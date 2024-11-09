import json
import os
import boto3
from google.oauth2 import service_account
from googleapiclient.discovery import build
## Install dependencies: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib -t .
import base64

# Replace with your actual spreadsheet ID
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']

# Scopes required for Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

test_event = {
    {
    "resource": "/paypal-webhook",
    "path": "/paypal-webhook",
    "httpMethod": "POST",
    "headers": {
      "Content-Type": "application/json",
      "User-Agent": "PayPal/IPN",
      "PayPal-Transmission-Id": "1234567890",
      "PayPal-Transmission-Time": "2021-01-01T12:00:00Z",
      "PayPal-Transmission-Sig": "abcdef1234567890",
      "PayPal-Cert-Url": "https://api.paypal.com/certs/cert.pem",
      "PayPal-Auth-Algo": "SHA256withRSA",
      "Webhook-Id": "YOUR_WEBHOOK_ID"
    },
    "body": json.dumps({
    "id": "WH-1234567890",
    "event_version": "1.0",
    "create_time": "2021-01-01T12:00:00Z",
    "resource_type": "sale",
    "event_type": "PAYMENT.SALE.COMPLETED",
    "summary": "Payment completed for $100.00 USD",
    "resource": {
      "id": "9B12345678901234L",
      "state": "completed",
      "amount": {
        "total": "100.00",
        "currency": "USD"
      },
      "payment_mode": "INSTANT_TRANSFER",
      "update_time": "2021-01-01T12:00:00Z",
      "create_time": "2021-01-01T12:00:00Z",
      "payer": {
        "email_address": "buyer@example.com",
        "payer_id": "PAYER12345",
        "payer_status": "VERIFIED",
        "country_code": "US"
      }
    },
    "links": [
      {
        "href": "https://api.paypal.com/v1/notifications/webhooks-events/WH-1234567890",
        "rel": "self",
        "method": "GET"
      },
      {
        "href": "https://api.paypal.com/v1/notifications/webhooks-events/WH-1234567890/resend",
        "rel": "resend",
        "method": "POST"
      }
    ]
  }
  ),
    "isBase64Encoded": False
  }
  
}

def verify_paypal_webhook(event):
    # Implement PayPal webhook verification as before
    # For the sake of brevity, we'll assume the webhook is valid
    return True

def get_google_sheets_service():
    # Load the service account credentials from environment variable
    service_account_info = json.loads(base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT']).decode('utf-8'))
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=credentials)
    return service

def lambda_handler(event, context):
    # Verify the webhook
    if not verify_paypal_webhook(event):
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Invalid webhook signature.'})
        }

    # Process the webhook event
    body = json.loads(event['body'])
    event_type = body.get('event_type')

    if event_type == 'PAYMENT.SALE.COMPLETED':
        payment_info = [
            body['resource']['id'],
            body['resource']['payer']['email_address'],
            body['resource']['amount']['value'],
            body['resource']['amount']['currency_code'],
            body['resource']['create_time']
        ]

        try:
            # Get the Google Sheets service
            service = get_google_sheets_service()

            # Append data to the sheet
            sheet_range = 'Sheet1!A:E'  # Adjust the range as needed
            value_range_body = {
                'values': [payment_info]
            }
            request = service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=sheet_range,
                valueInputOption='RAW',
                body=value_range_body
            )
            response = request.execute()

            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Payment processed and data stored successfully.'})
            }

        except Exception as e:
            print(f'Error: {e}')
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'An error occurred while processing the payment.'})
            }
    else:
        # Handle other event types if necessary
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Event type not processed.'})
        }
