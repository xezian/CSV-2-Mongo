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
    errors = []
    for row in reader:
        if len(row) != len(headers):
            errors.append(
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

        # Process invalid fields into errors
        # Create user update object with valid name, salary, manager_id, hire_date
        user_update = {}
        manager = None

        if not valid_email:
            errors.append(f"Invalid email: {entry['Email']}\nEntry unprocessable")
            # Skip ahead to the next record
            continue

        if valid_manager_email != "":  # If blank leave manager_id field alone
            # manager email is either a valid email or None at this point
            manager = db.user.find_one({"normalized_email": valid_manager_email})
            if manager:
                user_update["manager_id"] = manager["_id"]
            else:
                errors.append(
                    f"Invalid manager email: {entry['Manager']}\nEntry unprocessable"
                )
                # Skip ahead to the next record if bad manager email
                continue

        if valid_name:
            user_update["name"] = valid_name
        else:
            errors.append(f"Invalid name: {entry['Name']}\nContinuing update")

        if valid_salary:
            user_update["salary"] = valid_salary
        else:
            errors.append(f"Invalid salary: {entry['Salary']}\nContinuing update")

        if valid_hire_date:
            user_update["hire_date"] = valid_hire_date
        else:
            errors.append(f"Invalid hire date: {entry['Hire Date']}\nContinuing update")

        # Update/upsert
        updated = db.user.update(
            {"normalized_email": valid_email}, {"$set": user_update}, upsert=True
        )

        # Get updated/created counts from update/upsert record response
        if updated["updatedExisting"]:
            response_body["numUpdated"] += 1
        else:
            response_body["numCreated"] += 1

        user = db.user.find_one({"normalized_email": valid_email})
        managers = []
        if user.get("manager_id"):  # At least one person actually has no managers
            manager_chain = db.chain_of_command.find_one(
                {"user_id": user["manager_id"]}
            )
            managers = manager_chain["chain_of_command"]
            managers.append(user["manager_id"])
        db.chain_of_command.update(
            {"user_id": user["_id"]},
            {"$set": {"chain_of_command": managers}},
            upsert=True,
        )
    response_body["errors"] = errors
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

    if entry["Manager"].strip() == "":
        valid_manager_email = ""
    else:
        valid_manager_email = (
            entry["Manager"]
            if re.match(r"[^@]+@[^@]+\.[^@]+", entry["Manager"])
            else None
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
