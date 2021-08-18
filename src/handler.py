import json
import os
import csv
from dateutil.parser import parse
from pymongo import MongoClient

db_uri = os.environ.get("MONGO_DB_URI", "localhost")
db_name = os.environ.get("MONGO_DB_NAME", "new_hire_test")

db = MongoClient(db_uri)[db_name]

COLUMNS = ["Name", "Email", "Manager", "Salary", "Hire Date"]


def handle_csv_upload(event, context):
    response_body = {
        "numCreated": 0,
        "numUpdated": 0,
        "errors": [],
    }

    # Read csv and separate headers
    lines = event.splitlines()
    first_line = lines[0].split(",")
    reader = csv.reader(lines)

    # Check that there are headers
    if len(set(COLUMNS) - set(first_line)) == len(COLUMNS):
        # Assume we have no headers since all are missing
        headers = COLUMNS
    else:
        headers = next(reader)  # using the provided headers

        # Since we have headers, check that headers are the expected (sorted for consistency)
        missing = sorted(set(COLUMNS) - set(headers))
        extra = sorted(set(headers) - set(COLUMNS))
        if len(missing):
            response_body["errors"].append(f"Missing Columns: {', '.join(missing)}")
        if len(extra):
            response_body["errors"].append(f"Unexpected Columns: {', '.join(extra)}")

        # If we have errors at this point, return them with status 400
        if len(response_body["errors"]):
            return {"statusCode": 400, "body": json.dumps(response_body)}

    entries = []
    for row in reader:
        if len(row) != len(headers):
            print(row)
            print(headers)
            response_body["errors"].append(
                f"Row {reader.line_num - 1} unprocessable, wrong number of columns"
            )
        else:
            entries.append({header: cell for header, cell in zip(headers, row)})

    for entry in entries:
        print(entry)

    response = {"statusCode": 200, "body": json.dumps(response_body)}

    return response
