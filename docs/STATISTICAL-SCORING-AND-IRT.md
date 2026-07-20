# Statistical Scoring & Item Response Theory (IRT) Guide

This document describes the mathematical and statistical foundations of the **Bench** scoring system. It covers the 2-Parameter Logistic (2PL) Item Response Theory model, its Bayesian formulation using PyMC, convergence diagnostics, and the multi-objective Pareto optimization used for preset model routing.

---

## 1. Classical vs. Latent Capability Scoring

Traditional software evaluation harnesses rely on **raw accuracy** (the percentage of tests or tasks passed). However, this naive approach suffers from three major flaws:
1. **Task Difficulty Bias**: Passing a highly complex task (e.g., debugging a timing-dependent race condition) is treated identically to passing a simple format check.
2. **Task Selection Bias**: When comparing models that ran different subsets of tasks, raw averages are not comparable.
3. **Lack of Uncertainty Bounds**: A model that passes $1/1$ task has $100\%$ raw correctness, which is statistically meaningless compared to a model passing $30/36$ tasks ($83.3\%$).

To address these limitations, **Bench** implements **Item Response Theory (IRT)** alongside raw metrics, estimating a model's true latent capability ($\theta$) while adjusting for individual task difficulties and discrimination powers.

---

## 2. The 2-Parameter Logistic (2PL) IRT Model

Under the 2PL IRT model, the probability $P(X_{ij} = 1)$ that a model $i$ solves task $j$ correctly is modeled using a logistic link function:

$$P(X_{ij} = 1 \mid \theta_i, a_j, b_j) = \sigma\big(a_j (\theta_i - b_j)\big) = \frac{1}{1 + e^{-a_j (\theta_i - b_j)}}$$

Where:
*   $\theta_i \in \mathbb{R}$: The latent capability of model $i$. A higher $\theta$ indicates a stronger model.
*   $b_j \in \mathbb{R}$: The difficulty of task $j$. A higher $b$ requires a stronger model to have a $50\%$ probability of success.
*   $a_j > 0$: The discrimination parameter of task $j$. It measures how steep the probability curve is at the difficulty threshold. High discrimination means the task sharply separates stronger models from weaker ones.

```mermaid
graph TD
    subgraph Model Parameters
        Theta[Model Latent Capability: θ_i]
    end
    subgraph Task Parameters
        A[Discrimination: a_j]
        B[Difficulty: b_j]
    end
    Theta --> Prob[Probability of Success: P_ij]
    A --> Prob
    B --> Prob
    Prob --> Obs[Observed Outcome: X_ij ∈ {0, 1}]
```

### Scientific References:
*   Hambleton, R. K., Swaminathan, H., & Rogers, H. J. (1991). *Fundamentals of Item Response Theory*. Sage Publications.
*   Lord, F. M. (1980). *Applications of Item Response Theory to Practical Testing Problems*. Lawrence Erlbaum Associates.

---

## 3. Bayesian Formulation & MCMC Fitting

In the **Bench** IRT engine, we formulate the 2PL model hierarchically and sample the joint posterior using Markov Chain Monte Carlo (MCMC).

### Priors
To resolve scaling and rotation indeterminacy (standard for IRT models), we impose the following prior distributions:

$$\theta_i \sim \mathcal{N}(0, 1)$$
$$b_j \sim \mathcal{N}(0, 2)$$
$$a_j \sim \text{LogNormal}(0, 0.5)$$

*   The prior on $\theta_i$ centers the latent trait distribution around $0.0$ with standard deviation $1.0$, defining the capability scale.
*   The LogNormal prior on $a_j$ constrains task discrimination to be strictly positive ($a_j > 0$), ensuring that higher capability $\theta$ always increases the probability of success.

### Likelihood & Sparse Data Handling
Since not all models run all tasks, the outcome matrix is sparse. We map only the *observed* evaluations ($X_{ij}$) by flattening the coordinate arrays of models and tasks:

$$X_{\text{obs}, k} \sim \text{Bernoulli}\big(\sigma(a_{j_k} (\theta_{i_k} - b_{j_k}))\big)$$

### Sampling via NUTS
The posterior is sampled using the **No-U-Turn Sampler (NUTS)**, a state-of-the-art Hamiltonian Monte Carlo (HMC) algorithm that avoids random-walk behavior:

```python
import pymc as pm

with pm.Model() as model:
    # Priors
    theta = pm.Normal("theta", mu=0, sigma=1, shape=n_models)
    a = pm.LogNormal("a", mu=0, sigma=0.5, shape=n_tasks)
    b = pm.Normal("b", mu=0, sigma=2, shape=n_tasks)
    
    # Linear predictor mapping observed indices
    logit_p = a[task_indices_1d] * (theta[model_indices] - b[task_indices_1d])
    
    # Likelihood
    pm.Bernoulli(
        "y_obs",
        logit_p=logit_p,
        observed=observed_y,
    )
    
    # MCMC sampling
    trace = pm.sample(
        draws=n_samples,
        chains=n_chains,
        random_seed=seed,
        progressbar=False,
        return_inferencedata=True,
    )
```

### Scientific References:
*   Gelman, A., Carlin, J. B., Stern, H. S., Dunson, D. B., Vehtari, A., & Rubin, D. B. (2013). *Bayesian Data Analysis*. CRC Press.
*   Hoffman, M. D., & Gelman, A. (2014). *The No-U-Turn Sampler: Adaptively setting path lengths in Hamiltonian Monte Carlo*. Journal of Machine Learning Research, 15(1), 1593-1623.

---

## 4. MCMC Convergence Diagnostics & Fallbacks

Sampling from complex posteriors can occasionally run into convergence issues (e.g. if the outcome matrix is extremely small or has complete separation). **Bench** protects against bad fits using strict diagnostics:

1.  **Divergent Transitions Check**: If the sampler encounters steep curvature (divergences > 0), the geometry of the posterior is not fully explored.
2.  **$\hat{R}$ (Gelman-Rubin diagnostic)**: We check the variance between chains compared to the variance within chains. We assert $\hat{R} < 1.1$ for all variables.
3.  **Classical Fallback**: If fitting fails to converge or PyMC/ArviZ dependencies are missing, the engine automatically catches the error, outputs a traceback-free warning, and falls back to classical scoring (mean task pass rate).

---

## 5. Task Quality Banding (Item Analysis)

After fitting, tasks are classified into quality bands based on their posterior mean discrimination ($a$):

| Band | Threshold | Meaning |
| :--- | :--- | :--- |
| **High** | $a \ge 1.0$ | Highly predictive task. Excellent signaling power. |
| **Medium** | $0.5 \le a < 1.0$ | Moderate predictive power. Useful context. |
| **Low** | $0.2 \le a < 0.5$ | Poor predictive power. Weak signal. |
| **Cull** | $a < 0.2$ | Low predictive signal (candidates for removal to minimize run times). |

---

## 6. Multi-Objective Pareto Frontier

When selecting a model, capability ($\theta$) is not the only metric of interest. In production environments, **Latency** ($T$) and **Token Cost** ($C$) are equally important.

To identify optimal models, we compute the **Pareto Frontier** across three dimensions:
1.  **Maximize Capability**: $\theta_i$
2.  **Minimize Latency**: $T_i$ (seconds/task)
3.  **Minimize Cost**: $C_i$ ($/task)

### Domination Criterion
A model $A$ *dominates* model $B$ ($A \succ B$) if and only if:
*   Model $A$ is no worse than model $B$ on all three dimensions.
*   Model $A$ is strictly better than model $B$ on at least one dimension.

$$\forall d \in \{\theta, T, C\}, \quad f_d(A) \ge f_d(B) \quad \text{and} \quad \exists d \in \{\theta, T, C\}, \quad f_d(A) > f_d(B)$$

*(where latency and cost are inverted so that larger values are better).*

Models that are not dominated by any other model form the **Pareto Frontier** and are marked with a star (**★**) in the `balanced` preset output.

```
                  Cost ($)
                     ▲
                     │   ★ Model A (Cheap & Fast)
                     │
                     │          ★ Model B (Balanced)
                     │
                     │                 ★ Model C (High Capability, Expensive)
                     │       Dominated Model
                     └─────────────────────────────► Capability (θ)
```

### Scientific References:
*   Deb, K. (2001). *Multi-Objective Optimization using Evolutionary Algorithms*. John Wiley & Sons.
