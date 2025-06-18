#!/usr/bin/env python3

import argparse
import os

import requests
import yaml

API_CREATE_URL = "https://api.cloudns.net/monitoring/create.json"
API_GET_URL = "https://api.cloudns.net/monitoring/get-records.json"
API_UPDATE_URL = "https://api.cloudns.net/monitoring/update.json"
API_DELETE_URL = "https://api.cloudns.net/monitoring/delete.json"
API_CREATE_NOTIFICATION_URL = "https://api.cloudns.net/monitoring/add-notification.json"
API_LIST_NOTIFICATIONS_URL = (
    "https://api.cloudns.net/monitoring/list-notifications.json"
)
API_DELETE_NOTIFICATION_URL = (
    "https://api.cloudns.net/monitoring/delete-notification.json"
)

AUTH_ID = os.environ.get("CLOUDNS_AUTH_ID")
AUTH_PASSWORD = os.environ.get("CLOUDNS_AUTH_PASSWORD")

PAGERDUTY_EMAIL = os.environ.get("PAGERDUTY_EMAIL")


def build_payload(monitor, monitor_type, monitor_id=None):
    payload = {
        "auth-id": AUTH_ID,
        "auth-password": AUTH_PASSWORD,
        "name": monitor["name"],
        "check_type": monitor["check_type"],
        "ip": monitor.get("ip", ""),
        "status_change_checks": monitor.get("status_change_checks", 2),
        "monitoring_region": monitor.get("monitoring_region", "nam"),
        "host": monitor.get("host", ""),
        "port": monitor.get("port", ""),
        "check_period": monitor.get("check_period", 300),
        "state": monitor.get("state", 1),
        "ip_type": monitor.get("ip_type", 2),
    }

    if monitor_type == 'http':
        additional_payload = {
            "http_request_type": monitor.get("http_request_type", "GET"),
            "content_match": monitor.get("content_match", "exact"),
            "custom_header": monitor.get("custom_header", ""),
            "custom_header_value": monitor.get("custom_header_value", ""),
            "http_status_code": monitor.get("http_status_code", ""),
            "path": monitor.get("path", ""),
            "timeout": monitor.get("timeout", 5),
        }

        if monitor.get("content"):
            additional_payload["content"] = monitor.get("content")

        payload.update(additional_payload)

        if payload["path"] and payload["path"].startswith('/'):
            payload["path"] = payload["path"].replace("/", "", 1)

    if monitor_type == 'smtp':
        additional_payload = {
            "connection_security": monitor.get("connection_security", 2),
        }
        payload.update(additional_payload)

    if monitor_id:
        payload["id"] = monitor_id

    return payload


def get_existing_monitors():
    monitors = {}
    page = 1

    while True:
        response = requests.get(
            API_GET_URL,
            params={
                "auth-id": AUTH_ID,
                "auth-password": AUTH_PASSWORD,
                "rows-per-page": 10,
                "page": page,
            },
        )
        if response.status_code == 200:
            data = response.json()
            for _, value in data.items():
                monitors[value["name"]] = value

            if response._content == b"{}":
                break
            else:
                page += 1
        else:
            print(f"Failed to fetch monitors: {response.text}")
            break

    return monitors


def fetch_existing_notifications(monitor_id):
    notifications = []
    page = 1

    while True:
        response = requests.get(
            API_LIST_NOTIFICATIONS_URL,
            params={
                "auth-id": AUTH_ID,
                "auth-password": AUTH_PASSWORD,
                "rows-per-page": 10,
                "page": page,
                "id": monitor_id,
            },
        )
        if response.status_code == 200:
            data = response.json()

            for notification in data:
                notifications.append(notification)

            if data == []:
                break
            else:
                page += 1
        else:
            print(f"Failed to fetch monitors: {response.text}")
            break

    return notifications


def create_monitor(monitor, monitor_type):
    payload = build_payload(monitor, monitor_type)
    response = requests.post(API_CREATE_URL, data=payload)
    if response.json()["status"] == "Success":
        print(f"Monitor '{monitor['name']}' created successfully.")

        return response.json()["id"]
    else:
        print(f"Failed to create monitor '{monitor['name']}': {response.text}")


def create_notification(
    monitor_id, monitor_name, notification_type, notification_value
):
    notification_payload = {
        "auth-id": AUTH_ID,
        "auth-password": AUTH_PASSWORD,
        "id": monitor_id,
        "type": notification_type,
        "value": notification_value,
    }

    response = requests.post(API_CREATE_NOTIFICATION_URL, data=notification_payload)
    if response.json()["status"] == "Success":
        print(f"Notification for monitor '{monitor_name}' created successfully.")
    else:
        print(
            f"Failed to create notification for monitor '{monitor_name}': {response.text}"
        )


def update_monitor(monitor_id, monitor_type, monitor):
    payload = build_payload(monitor, monitor_type, monitor_id)
    response = requests.post(API_UPDATE_URL, data=payload)
    if response.json()["status"] == "Success":
        print(f"Monitor '{monitor['name']}' updated successfully.")
    else:
        print(f"Failed to update monitor '{monitor['name']}': {response.text}")


def delete_monitor(monitor_id):
    response = requests.post(
        API_DELETE_URL,
        data={"auth-id": AUTH_ID, "auth-password": AUTH_PASSWORD, "id": monitor_id},
    )
    if response.json()["status"] == "Success":
        print(f"Monitor ID {monitor_id} deleted successfully.")
    else:
        print(f"Failed to delete monitor ID {monitor_id}: {response.text}")


def mon_requires_update(fetched_monitor, local_monitor):
    for key, value in local_monitor.items():
        if isinstance(value, int):
            value = str(value)
        if key == "path":
            value = value.replace("/", "", 1)
        if key in fetched_monitor and fetched_monitor[key] != value:
            return True
    return False


def mon_notification_requires_update(fetched_notifications, local_notifications):
    for notification in local_notifications:
        local_type = notification.get("type")
        local_value = notification.get("value")

        if local_type is None or local_value is None:
            continue

        for fetched_notification in fetched_notifications:
            fetched_type = fetched_notification.get("type")
            fetched_value = fetched_notification.get("value")

            if local_type == fetched_type and local_value != fetched_value:
                return True

    return False


def delete_notification(monitor_id, notification_id):
    response = requests.post(
        API_DELETE_NOTIFICATION_URL,
        data={
            "auth-id": AUTH_ID,
            "auth-password": AUTH_PASSWORD,
            "id": monitor_id,
            "notification-id": notification_id,
        },
    )
    if response.json()["status"] == "Success":
        print(f"Notification ID {notification_id} deleted successfully.")
    else:
        print(f"Failed to delete notification ID {notification_id}: {response.text}")


def parse_yaml_and_manage_monitors(yaml_file):
    if yaml_file is None:
        print("Please provide the path to the YAML configuration file.")
        return

    if os.path.exists(yaml_file) is False:
        print(f"File '{yaml_file}' not found.")
        return

    with open(yaml_file, "r") as file:
        monitors = yaml.safe_load(file)

    if monitors is None:
        print("No monitors found in the YAML file.")
        return

    existing_monitors = get_existing_monitors()

    for mon in monitors:
        if mon["check_type"] == 5:
            mon_type = 'http'
        elif mon["check_type"] == 15:
            mon_type = 'smtp'

        if mon["name"] in existing_monitors.keys():
            if mon_requires_update(existing_monitors[mon["name"]], mon):
                update_monitor(existing_monitors[mon["name"]]["id"], mon_type, mon)

            existing_notification = fetch_existing_notifications(
                existing_monitors[mon["name"]]["id"]
            )
            if len(existing_notification) == 0:
                for notification in mon.get(
                    "notifications", [{"type": "mail", "value": PAGERDUTY_EMAIL}]
                ):
                    create_notification(
                        existing_monitors[mon["name"]]["id"],
                        mon["name"],
                        notification["type"],
                        notification["value"],
                    )
            else:
                if mon_notification_requires_update(
                    existing_notification,
                    mon.get(
                        "notifications", [{"type": "mail", "value": PAGERDUTY_EMAIL}]
                    ),
                ):
                    for _notification in existing_notification:
                        delete_notification(
                            existing_monitors[mon["name"]]["id"],
                            _notification["notification_id"],
                        )
                    for notification in mon.get(
                        "notifications", [{"type": "mail", "value": PAGERDUTY_EMAIL}]
                    ):
                        create_notification(
                            existing_monitors[mon["name"]]["id"],
                            mon["name"],
                            notification["type"],
                            notification["value"],
                        )
        else:
            id = create_monitor(mon, mon_type)
            for notification in mon.get(
                "notifications", [{"type": "mail", "value": PAGERDUTY_EMAIL}]
            ):
                create_notification(
                    id, mon["name"], notification["type"], notification["value"]
                )

    for name, monitor in existing_monitors.items():
        if name not in [mon["name"] for mon in monitors]:
            delete_monitor(monitor["id"])


def main():
    parser = argparse.ArgumentParser(
        description="Manage monitoring checks based on a YAML configuration file."
    )
    parser.add_argument(
        "--monitors-file",
        type=str,
        help="Path to the YAML configuration file (default: monitors.yaml)",
        dest="yaml_file",
    )
    args = parser.parse_args()
    parse_yaml_and_manage_monitors(args.yaml_file)


if __name__ == "__main__":
    main()
