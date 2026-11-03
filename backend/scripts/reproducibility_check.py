
import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="starter")
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    outputs = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for folder in ["run_1", "run_2"]:
            target = temp_path / folder

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.scripts.generate_data",
                    "--scale", args.scale,
                    "--seed", str(args.seed),
                    "--out", str(target),
                ],
                cwd=project_root,
                check=True,
            )

            outputs.append(target)

        files_1 = sorted(
            p.name for p in outputs[0].glob("*.csv")
        )
        files_2 = sorted(
            p.name for p in outputs[1].glob("*.csv")
        )

        if files_1 != files_2:
            raise RuntimeError("Generated CSV file lists differ")

        differences = []

        for filename in files_1:
            hash_1 = file_hash(outputs[0] / filename)
            hash_2 = file_hash(outputs[1] / filename)

            if hash_1 != hash_2:
                differences.append(filename)

        if differences:
            print("REPRODUCIBILITY FAILED")
            print("Different files:", differences)
            sys.exit(1)

        print("REPRODUCIBILITY PASSED")
        print("Scale:", args.scale)
        print("Seed:", args.seed)
        print("CSV files checked:", len(files_1))
        print("All CSV hashes match.")


if __name__ == "__main__":
    main()
