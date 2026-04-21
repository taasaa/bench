"""CLI tool with swapped positional arguments."""
import argparse
import sys


def process_files(input_file: str, output_file: str) -> str:
    """Read input file, process contents, write to output file."""
    with open(input_file) as f:
        data = f.read()

    # Simple processing: uppercase and add line numbers
    lines = data.splitlines()
    result = "\n".join(f"{i+1}: {line.upper()}" for i, line in enumerate(lines))

    with open(output_file, "w") as f:
        f.write(result)

    return f"Processed {len(lines)} lines: {input_file} -> {output_file}"


def main():
    parser = argparse.ArgumentParser(description="Process text files.")
    # Bug: arguments are swapped — first positional should be input, second output
    # But the help text says the opposite of what the code actually does
    parser.add_argument("output_file", help="Input file to read from")
    parser.add_argument("input_file", help="Output file to write to")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    try:
        result = process_files(args.input_file, args.output_file)
        if args.verbose:
            print(result)
        print("Done.")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
