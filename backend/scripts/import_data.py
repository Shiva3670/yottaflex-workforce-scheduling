
import csv
import getpass
from pathlib import Path

import mysql.connector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

DATABASE = "yottaflex_workforce"
HOST = "127.0.0.1"
USER = "root"

# Parent tables must be imported before child tables.
IMPORT_ORDER = [
    "team",
    "skill",
    "shift_template",
    "employee",
    "employee_skill",
    "holiday_calendar",
    "shift",
    "coverage_requirement",
    "leave_request",
    "shift_assignment",
    "attendance_event",
    "swap_request",
]

# Reverse dependency order for safe re-imports.
DELETE_ORDER = list(reversed(IMPORT_ORDER))

BOOLEAN_COLUMNS = {
    "active",
    "is_overnight",
    "coverage_gap",
}


def convert_value(column, value):
    if value == "":
        return None

    if column in BOOLEAN_COLUMNS:
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0

    # MySQL accepts DATETIME strings with a space separator.
    if "T" in value and (
        column.endswith("_at") or column in ("start_at", "end_at")
    ):
        return value.replace("T", " ", 1)

    return value


def main():
    password = getpass.getpass("Enter MySQL root password: ")

    connection = mysql.connector.connect(
        host=HOST,
        user=USER,
        password=password,
        database=DATABASE,
    )

    cursor = connection.cursor()

    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Remove old records so rerunning the script is safe.
        for table in DELETE_ORDER:
            cursor.execute(f"DELETE FROM `{table}`")

        connection.commit()

        total_rows = 0

        for table in IMPORT_ORDER:
            csv_path = DATA_DIR / f"{table}.csv"

            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Missing CSV file: {csv_path}"
                )

            with csv_path.open(
                "r", newline="", encoding="utf-8-sig"
            ) as file:
                reader = csv.DictReader(file)
                columns = reader.fieldnames

                if not columns:
                    raise ValueError(f"No columns found in {csv_path}")

                rows = [
                    tuple(
                        convert_value(column, row[column])
                        for column in columns
                    )
                    for row in reader
                ]

            if not rows:
                print(f"{table}: 0 rows")
                continue

            column_sql = ", ".join(
                f"`{column}`" for column in columns
            )
            placeholders = ", ".join(["%s"] * len(columns))

            query = (
                f"INSERT INTO `{table}` ({column_sql}) "
                f"VALUES ({placeholders})"
            )

            cursor.executemany(query, rows)

            inserted = cursor.rowcount
            total_rows += inserted

            print(f"{table}: {inserted} rows inserted")

        connection.commit()

        print("\nDATA IMPORT SUCCESSFUL")
        print(f"Total rows inserted: {total_rows}")

    except Exception:
        connection.rollback()
        print("\nIMPORT FAILED. Transaction rolled back.")
        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
