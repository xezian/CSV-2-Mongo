import json
import os
import re
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

    # Create a list of dicts of rows, ignore rows with wrong number of columns
    entries = []
    for row in reader:
        if len(row) != len(headers):
            response_body["errors"].append(
                f"Row {reader.line_num - 1} unprocessable, wrong number of columns"
            )
        else:
            entries.append({header: cell for header, cell in zip(headers, row)})

    # Loop through list of row dicts
    for entry in entries:
        (
            valid_email,
            valid_name,
            valid_salary,
            valid_manager_email,
            valid_hire_date,
        ) = validate_entry(entry)

        # Process validated fields into errors
        if not valid_email:
            response_body["errors"].append(
                f"Invalid email: {entry['Email']}\nEntry unprocessable"
            )
            # Skip ahead to the next record
            continue

        if not valid_name:
            response_body["errors"].append(
                f"Invalid name: {entry['Name']}\nContinuing Update"
            )
        if not valid_salary:
            response_body["errors"].append(
                f"Invalid salary: {entry['Salary']}\nContinuing Update"
            )
        if not valid_hire_date:
            response_body["errors"].append(
                f"Invalid hire date: {entry['Hire Date']}\nContinuing Update"
            )

        update_user = {}
        manager = None
        # Update name, salary, manager_id, hire_date
        if valid_name:
            update_user["name"] = valid_name
        if valid_salary:
            update_user["salary"] = valid_salary
        if valid_manager_email:
            manager = db.user.find_one({"normalized_email": valid_manager_email})
            if manager:
                update_user["manager_id"] = manager["_id"]
        if valid_hire_date:
            update_user["hire_date"] = valid_hire_date

        updated = db.user.update(
            {"normalized_email": valid_email}, {"$set": update_user}, upsert=True
        )
        if updated["updatedExisting"]:
            response_body["numUpdated"] += 1
        else:
            response_body["numCreated"] += 1

        user = db.user.find_one({"normalized_email": valid_email})
        managers = []
        if manager:
            manager_chain = db.chain_of_command.find_one({"user_id": manager["_id"]})
            managers = manager_chain["chain_of_command"]
            managers.append(manager["_id"])
        db.chain_of_command.update(
            {"user_id": user["_id"]},
            {"$set": {"chain_of_command": managers}},
            upsert=True,
        )
    response = {"statusCode": 200, "body": json.dumps(response_body)}
    return response


def validate_entry(entry):
    # Validate fields
    valid_email = (
        entry["Email"] if re.match(r"[^@]+@[^@]+\.[^@]+", entry["Email"]) else None
    )
    valid_name = (
        entry["Name"]
        if all(x.isalpha() or x.isspace() for x in entry["Name"])
        else None
    )
    valid_salary = validate_salary(entry["Salary"])
    valid_manager_email = (
        entry["Manager"] if re.match(r"[^@]+@[^@]+\.[^@]+", entry["Manager"]) else None
    )
    valid_hire_date = validate_hire_date(entry["Hire Date"])
    return valid_email, valid_name, valid_salary, valid_manager_email, valid_hire_date


def validate_salary(salary):
    """Returns a valid salary entry"""
    try:
        valid_salary = int(str(salary).replace(",", "").split(".")[0])
    except ValueError:
        valid_salary = None
    return valid_salary


def validate_hire_date(hire_date):
    """Returns a valid hire date"""
    try:
        valid_hire_date = parse(hire_date)
    except ValueError:
        valid_hire_date = None
    return valid_hire_date
