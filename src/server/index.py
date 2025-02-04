import boto3
import json
import logging
import requests
import jwt
import os
from dotenv import load_dotenv

load_dotenv()

client = boto3.client('cognito-idp', region_name='us-west-1')
ses = boto3.client('ses', region_name='us-west-1')

environment = os.getenv('ENVIRONMENT')
domain_name = os.getenv('DOMAIN_NAME')

# Configuration
def get_ssm_parameter(name):
    ssm = boto3.client('ssm')
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response['Parameter']['Value']

USER_POOL_ID = get_ssm_parameter(f'/rcw-client-backend-{environment}/COGNITO_USER_POOL_ID')
USER_POOL_CLIENT_ID = get_ssm_parameter(f'/rcw-client-backend-{environment}/COGNITO_CLIENT_ID')
PAYPAL_CLIENT_ID = get_ssm_parameter(f'/rcw-client-backend-{environment}/PAYPAL_CLIENT_ID')
PAYPAL_SECRET = get_ssm_parameter(f'/rcw-client-backend-{environment}/PAYPAL_SECRET')
SENDER_EMAIL = get_ssm_parameter(f'/rcw-client-backend-{environment}/SESIdentitySenderParameter')
RECIPIENT_EMAIL = get_ssm_parameter(f'/rcw-client-backend-{environment}/SESRecipientParameter')
ALLOW_ORIGIN = domain_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        http_method = event['httpMethod']
        resource_path = event['path']

        if http_method == "OPTIONS":
            return cors_response(200, {})
        
        if http_method == 'GET' or http_method == 'DELETE':
            query_params = event.get('queryStringParameters', {}) or {}
            email = query_params.get('email')
        else:
            body = json.loads(event.get('body', "{}"))
            email = body.get('email')
            password = body.get('password')
            first_name = body.get('first_name')
            last_name = body.get('last_name')
            confirmation_code = body.get('confirmation_code')
            access_token = body.get('access_token')
            new_password = body.get('new_password')
            attribute_updates = body.get('attribute_updates', {})
            message = body.get('message')
            custom_id = body.get('custom_id')
            amount = body.get('amount')

        # Routing based on the resource path and HTTP method
        if resource_path == "/signup" and http_method == "POST":
            return sign_up(password, email, first_name, last_name)
        elif resource_path == "/confirm" and http_method == "POST":
            return confirm_user(email)
        elif resource_path == "/confirm-email" and http_method == "POST":
            return confirm_email(access_token, confirmation_code)
        elif resource_path == "/confirm-email-resend" and http_method == "POST":
            return confirm_email_resend(access_token)
        elif resource_path == "/login" and http_method == "POST":
            return log_in(email, password)
        elif resource_path == "/forgot-password" and http_method == "POST":
            return forgot_password(email)
        elif resource_path == "/confirm-forgot-password" and http_method == "POST":
            return confirm_forgot_password(email, confirmation_code, new_password)
        elif resource_path == "/user" and http_method == "GET":
            return get_user(email)
        elif resource_path == "/user" and http_method == "PATCH":
            return update_user(email, attribute_updates)
        elif resource_path == "/user" and http_method == "DELETE":
            return delete_user(email)
        elif resource_path == "/contact-us" and http_method == "POST":
            return contact_us(first_name, email, message)
        elif resource_path == "/create-paypal-order" and http_method == "POST":
            currency = body.get('currency', "USD")
            return create_paypal_order_route(amount, custom_id, currency)
        elif resource_path == "/create-paypal-subscription" and http_method == "POST":
            user_name = body.get('user_name')
            return create_paypal_subscription_route(amount, custom_id)
        elif http_method == "OPTIONS":
            return cors_response(200, {"message": "CORS preflight successful"})
        else:
            return cors_response(404, {"message": "Resource not found"})
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return cors_response(500, {"message": str(e)})

# Helper function to add CORS headers
def cors_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            #"Access-Control-Allow-Credentials": "true"

        },
        "body": json.dumps(body)
    }

# User Sign-Up
def sign_up(password, email, first_name, last_name):
    if not all([email, password, first_name, last_name]):
        return cors_response(400, {"message": "Email, password, first name, and last name are required"})
    try:
        client.sign_up(
            ClientId=USER_POOL_CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'custom:firstName', 'Value': first_name},
                {'Name': 'custom:lastName', 'Value': last_name}
            ]
        )
        return cors_response(200, {"message": "User signed up successfully"})
    except client.exceptions.UsernameExistsException:
        return cors_response(409, {
            "message": "User already exists",
            "errorType": "UserAlreadyExists"
        })
    except client.exceptions.AliasExistsException:
        return cors_response(409, {
            "message": "A user with this email or phone number already exists.",
            "errorType": "AliasExists"
        })
    except client.exceptions.InvalidPasswordException as e:
        return cors_response(400, {
            "message": e.response['Error']['Message'],
            "errorType": "InvalidPassword"
        })
    except client.exceptions.InvalidParameterException as e:
        return cors_response(400, {
            "message": e.response['Error']['Message'],
            "errorType": "InvalidParameter"
        })
    except client.exceptions.TooManyRequestsException:
        return cors_response(429, {
            "message": "Too many requests. Please try again later.",
            "errorType": "TooManyRequests"
        })
    except client.exceptions.CodeDeliveryFailureException:
        return cors_response(500, {
            "message": "Failed to send confirmation code. Please try again.",
            "errorType": "CodeDeliveryFailure"
        })
    except client.exceptions.UserLambdaValidationException as e:
        return cors_response(400, {
            "message": e.response['Error']['Message'],
            "errorType": "LambdaValidationFailed"
        })
    except Exception as e:
        logger.error(f"Error in sign_up: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An internal server error occurred",
            "errorType": "InternalError"
        })

# Confirm User
def confirm_user(email):
    try:
        client.admin_confirm_sign_up(
            UserPoolId=USER_POOL_ID,
            Username=email
        )
        return cors_response(200, {"message": "User confirmed successfully"})
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We could not find a user with this email address.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(403, {
            "message": "You do not have the necessary permissions to confirm this user.",
            "errorType": "NotAuthorized"
        })
    except Exception as e:
        logger.error(f"Error in confirm_user: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "Something went wrong while confirming the user. Please try again later.",
            "errorType": "InternalError"
        })

def confirm_email(access_token, confirmation_code):
    try:
        client.verify_user_attribute(
            AccessToken=access_token,
            AttributeName='email',
            Code=confirmation_code
        )
        return cors_response(200, {"message": "Email confirmed successfully."})
    except client.exceptions.CodeMismatchException:
        return cors_response(400, {
            "message": "The confirmation code you entered is incorrect. Please check and try again.",
            "errorType": "CodeMismatch"
        })
    except client.exceptions.ExpiredCodeException:
        return cors_response(400, {
            "message": "The confirmation code has expired. Please request a new code and try again.",
            "errorType": "ExpiredCode"
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(403, {
            "message": "You are not authorized to perform this action. Please ensure you are logged in and try again.",
            "errorType": "NotAuthorized"
        })
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We couldn't find a user associated with this request. Please check your details and try again.",
            "errorType": "UserNotFound"
        })
    except Exception as e:
        logger.error(f"Error in confirm_email: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while confirming your email. Please try again later.",
            "errorType": "InternalError"
        })

def confirm_email_resend(access_token):
    try:
        client.get_user_attribute_verification_code(
            AccessToken=access_token,
            AttributeName='email'
        )
        return cors_response(200, {"message": "Verification code sent successfully."})
    except client.exceptions.LimitExceededException:
        return cors_response(429, {
            "message": "You have exceeded the number of allowed attempts. Please wait before trying again.",
            "errorType": "LimitExceeded"
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(403, {
            "message": "You are not authorized to request a new verification code. Please log in and try again.",
            "errorType": "NotAuthorized"
        })
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We could not find a user associated with this request. Please check your details and try again.",
            "errorType": "UserNotFound"
        })
    except Exception as e:
        logger.error(f"Error in confirm_email_resend: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while trying to resend the verification code. Please try again later.",
            "errorType": "InternalError"
        })

# User Log-In
def log_in(email, password):
    if not all([email, password]):
        return cors_response(400, {"message": "Email and password are required"})
    try:
        response = client.initiate_auth(
            ClientId=USER_POOL_CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': email,
                'PASSWORD': password
            }
        )

        id_token = response['AuthenticationResult']['IdToken']
        
        decoded_token = jwt.decode(id_token, options={"verify_signature": False})
        user_id = decoded_token.get("sub")
        
        return cors_response(200, {
            "message": "User logged in successfully",
            "user_id": user_id,
            "id_token": id_token,
            "access_token": response['AuthenticationResult']['AccessToken'],
            "refresh_token": response['AuthenticationResult']['RefreshToken']
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(401, {
            "message": "The email or password provided is incorrect. Please try again.",
            "errorType": "NotAuthorized"
        })
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We couldn't find a user with this email address. Please check the email entered or sign up if you don't have an account.",
            "errorType": "UserNotFound"
        })
    except Exception as e:
        logger.error(f"Error in log_in: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while attempting to log in. Please try again later.",
            "errorType": "InternalError"
        })

# Forgot Password (Initiate)
def forgot_password(email):
    try:
        client.forgot_password(
            ClientId=USER_POOL_CLIENT_ID,
            Username=email
        )
        return cors_response(200, {"message": "Password reset initiated. Check your email for the code."})
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We could not find an account associated with this email address.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.LimitExceededException:
        return cors_response(429, {
            "message": "You have exceeded the number of allowed attempts. Please wait a while before trying again.",
            "errorType": "LimitExceeded"
        })
    except client.exceptions.NotAuthorizedException as e:
        message = e.response['Error']['Message']
        return cors_response(403, {
            "message": message,
            "errorType": "NotAuthorized"
        })
    except Exception as e:
        logger.error(f"Error in forgot_password: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while initiating the password reset. Please try again later.",
            "errorType": "InternalError"
        })

# Confirm Forgot Password
def confirm_forgot_password(email, confirmation_code, new_password):
    try:
        client.confirm_forgot_password(
            ClientId=USER_POOL_CLIENT_ID,
            Username=email,
            ConfirmationCode=confirmation_code,
            Password=new_password
        )
        return cors_response(200, {"message": "Password reset successfully."})
    except client.exceptions.CodeMismatchException:
        return cors_response(400, {
            "message": "The confirmation code you entered is incorrect. Please check the code and try again.",
            "errorType": "CodeMismatch"
        })
    except client.exceptions.ExpiredCodeException:
        return cors_response(400, {
            "message": "The confirmation code has expired. Please request a new code and try again.",
            "errorType": "ExpiredCode"
        })
    except client.exceptions.InvalidPasswordException as e:
        message = e.response['Error']['Message']
        return cors_response(400, {
            "message": f"Your new password is invalid: {message}. Please ensure it meets the required criteria.",
            "errorType": "InvalidPassword"
        })
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "We could not find an account associated with this email address. Please check your details.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.LimitExceededException:
        return cors_response(429, {
            "message": "You have made too many attempts. Please wait a while before trying again.",
            "errorType": "LimitExceeded"
        })
    except Exception as e:
        logger.error(f"Error in confirm_forgot_password: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while resetting your password. Please try again later.",
            "errorType": "InternalError"
        })

# Get User Data
def get_user(email):
    if not email:
        return cors_response(400, {"message": "Missing required 'email' query parameter"})
    try:
        response = client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=email
        )
        user_attributes = {attr['Name']: attr['Value'] for attr in response['UserAttributes']}
        return cors_response(200, {"message": "User data retrieved successfully", "user_attributes": user_attributes})
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "The requested user could not be found. Please check the provided details and try again.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.InvalidParameterException:
        return cors_response(400, {
            "message": "The input parameters are invalid. Please verify the information and try again.",
            "errorType": "InvalidParameter"
        })
    except client.exceptions.TooManyRequestsException:
        return cors_response(429, {
            "message": "Too many requests have been made in a short period. Please wait a while before retrying.",
            "errorType": "TooManyRequests"
        })
    except Exception as e:
        logger.error(f"Unexpected error in get_user: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while retrieving the user. Please try again later.",
            "errorType": "InternalServerError"
        })

# Update User Attributes
def update_user(email, attribute_updates):
    if not email:
        return cors_response(400, {"message": "Email is required"})
    if not attribute_updates:
        return cors_response(400, {"message": "Attribute updates are required"})
    try:
        attributes = [{'Name': key, 'Value': value} for key, value in attribute_updates.items()]
        client.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=attributes
        )
        return cors_response(200, {"message": "User attributes updated successfully"})
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "No user was found with the provided email address.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.InvalidParameterException as e:
        message = e.response['Error']['Message']
        return cors_response(400, {
            "message": f"Invalid parameter: {message}. Please verify your input and try again.",
            "errorType": "InvalidParameter"
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(403, {
            "message": "You are not authorized to update this user's attributes. Please check your permissions.",
            "errorType": "NotAuthorized"
        })
    except Exception as e:
        logger.error(f"Unexpected error in update_user: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while updating the user attributes. Please try again later.",
            "errorType": "InternalError"
        })

# Delete User
def delete_user(email):
    if not email:
        return cors_response(400, {"message": "Email is required"})
    try:
        client.admin_delete_user(
            UserPoolId=USER_POOL_ID,
            Username=email
        )
        return cors_response(200, {"message": "User deleted successfully"})
    except client.exceptions.UserNotFoundException:
        return cors_response(404, {
            "message": "No user was found with the provided email address. Please check and try again.",
            "errorType": "UserNotFound"
        })
    except client.exceptions.NotAuthorizedException:
        return cors_response(403, {
            "message": "You are not authorized to delete this user. Please check your permissions.",
            "errorType": "NotAuthorized"
        })
    except Exception as e:
        logger.error(f"Unexpected error in delete_user: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while attempting to delete the user. Please try again later.",
            "errorType": "InternalError"
        })

def contact_us(first_name, email, message):
    if not all([first_name, email, message]):
        return cors_response(400, {"message": "All fields are required: name, email, and message."})

    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [RECIPIENT_EMAIL]},
            Message={
                'Subject': {'Data': 'Contact Us Form Submission'},
                'Body': {
                    'Text': {'Data': f'Name: {first_name}\nEmail: {email}\nMessage: {message}'}
                }
            }
        )
        return cors_response(200, {"message": "Message sent successfully."})
    except ses.exceptions.MessageRejected as e:
        logger.error(f"Message rejected: {str(e)}", exc_info=True)
        return cors_response(400, {
            "message": "The email message was rejected. Please ensure the provided email address is valid.",
            "errorType": "MessageRejected"
        })
    except ses.exceptions.MailFromDomainNotVerifiedException as e:
        logger.error(f"Email address not verified: {str(e)}", exc_info=True)
        return cors_response(400, {
            "message": "The sender's email address has not been verified. Please contact support for assistance.",
            "errorType": "EmailNotVerified"
        })
    except ses.exceptions.ConfigurationSetDoesNotExistException as e:
        logger.error(f"Configuration set issue: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "There was a configuration issue with the email service. Please try again later.",
            "errorType": "ConfigurationError"
        })
    except Exception as e:
        logger.error(f"Unhandled error in contact_us: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while sending your message. Please try again later.",
            "errorType": "InternalError"
        })

# Get Paypal Access Token
def get_paypal_access_token():
    url = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
    }
    data = {
        "grant_type": "client_credentials"
    }
    auth = (PAYPAL_CLIENT_ID, PAYPAL_SECRET)

    try:
        response = requests.post(url, headers=headers, data=data, auth=auth, timeout=10)

        if response.status_code == 200:
            token_data = response.json()
            return token_data["access_token"]
        else:
            error_details = response.json()
            logger.error(f"PayPal token error: {error_details}")
            return cors_response(response.status_code, {
                "message": "Failed to retrieve PayPal access token.",
                "errorType": "PayPalAPIError",
                "details": error_details
            })
    except requests.exceptions.Timeout:
        logger.error("PayPal API request timed out.")
        return cors_response(504, {
            "message": "The request to the PayPal API timed out. Please try again later.",
            "errorType": "TimeoutError"
        })
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while connecting to PayPal API.")
        return cors_response(503, {
            "message": "Unable to connect to the PayPal API. Please check your network and try again.",
            "errorType": "ConnectionError"
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"Unhandled request exception: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while connecting to the PayPal API.",
            "errorType": "RequestError"
        })
    except Exception as e:
        logger.error(f"Unexpected error in get_paypal_access_token: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while retrieving the PayPal access token.",
            "errorType": "InternalError"
        })

# Create Paypal Order
def create_paypal_order(amount, custom_id, currency="USD"):
    try:
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("Failed to retrieve PayPal access token.")
            return cors_response(500, {
                "message": "Failed to retrieve PayPal access token.",
                "errorType": "AccessTokenError"
            })

        url = "https://api-m.sandbox.paypal.com/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount)
                    },
                    "custom_id": custom_id
                }
            ]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 201:
            return cors_response(201, {
                "order": response.json()
            })
        else:
            error_details = response.json()
            logger.error(f"PayPal order error: {error_details}")
            return cors_response(response.status_code, {
                "message": f"Failed to create PayPal order: {error_details.get('name', 'Unknown error')} - {error_details.get('message', 'No description')}.",
                "errorType": "PayPalAPIError",
                "details": error_details
            })
    except requests.exceptions.Timeout:
        logger.error("PayPal API request timed out.")
        return cors_response(504, {
            "message": "The request to the PayPal API timed out. Please try again later.",
            "errorType": "TimeoutError"
        })
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while connecting to PayPal API.")
        return cors_response(503, {
            "message": "Unable to connect to the PayPal API. Please check your network and try again.",
            "errorType": "ConnectionError"
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"Unhandled request exception: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while connecting to the PayPal API.",
            "errorType": "RequestError"
        })
    except Exception as e:
        logger.error(f"Unexpected error in create_paypal_order: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while creating the PayPal order. Please try again later.",
            "errorType": "InternalError"
        })

# Create Paypal Order Route
def create_paypal_order_route(amount, custom_id, currency="USD"):
    try:
        if amount <= 0:
            raise ValueError("The amount must be greater than zero.")
        if not isinstance(custom_id, str) or not custom_id.strip():
            raise ValueError("The Custom ID must be a non-empty string.")

        order = create_paypal_order(amount, custom_id, currency)

        if "id" not in order:
            logger.error("PayPal order response missing 'id' field.")
            return cors_response(500, {
                "message": "PayPal order creation succeeded, but the response is incomplete.",
                "errorType": "IncompleteResponse"
            })

        return cors_response(200, {
            "id": order["id"],
            "message": "PayPal order created successfully."
        })

    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        return cors_response(400, {
            "message": str(ve),
            "errorType": "ValidationError"
        })

    except requests.exceptions.RequestException as re:
        logger.error(f"Request exception during PayPal order creation: {str(re)}")
        return cors_response(503, {
            "message": "A network error occurred while connecting to PayPal. Please try again later.",
            "errorType": "NetworkError"
        })

    except Exception as e:
        logger.error(f"Unexpected error creating PayPal order: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while processing your request. Please try again later.",
            "errorType": "InternalError"
        })

# Create Paypal Product
def create_paypal_product():
    try:
        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("Failed to retrieve PayPal access token.")
            return cors_response(500, {
                "message": "Failed to retrieve PayPal access token.",
                "errorType": "AccessTokenError"
            })

        url = "https://api-m.sandbox.paypal.com/v1/catalogs/products"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "name": "Donation Product",
            "description": "A product for donation subscriptions.",
            "type": "SERVICE",
            "category": "CHARITY"
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 201:
            product_id = response.json().get("id")
            if not product_id:
                logger.error("PayPal product created, but no product ID returned.")
                return cors_response(500, {
                    "message": "Product creation succeeded, but the response is incomplete.",
                    "errorType": "IncompleteResponse"
                })
            return product_id
        else:
            error_details = response.json()
            logger.error(f"PayPal product creation failed: {error_details}")
            return cors_response(response.status_code, {
                "message": f"Failed to create PayPal product: {error_details.get('name', 'Unknown error')} - {error_details.get('message', 'No description')}.",
                "errorType": "PayPalAPIError",
                "details": error_details
            })
    except requests.exceptions.Timeout:
        logger.error("PayPal API request timed out.")
        return cors_response(504, {
            "message": "The request to the PayPal API timed out. Please try again later.",
            "errorType": "TimeoutError"
        })
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while connecting to PayPal API.")
        return cors_response(503, {
            "message": "Unable to connect to the PayPal API. Please check your network and try again.",
            "errorType": "ConnectionError"
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"Unhandled request exception: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while connecting to the PayPal API.",
            "errorType": "RequestError"
        })
    except Exception as e:
        logger.error(f"Unexpected error in create_paypal_product: {e}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while creating the PayPal product. Please try again later.",
            "errorType": "InternalError"
        })

# Create Paypal Plan
def create_paypal_plan(product_id, amount):
    try:
        if not product_id:
            logger.error("Product ID is required to create a PayPal plan.")
            return cors_response(400, {
                "message": "Product ID is required to create a PayPal plan.",
                "errorType": "ValidationError"
            })

        if amount <= 0:
            logger.error("Amount must be greater than zero.")
            return cors_response(400, {
                "message": "Amount must be greater than zero.",
                "errorType": "ValidationError"
            })

        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("Failed to retrieve PayPal access token.")
            return cors_response(500, {
                "message": "Failed to retrieve PayPal access token.",
                "errorType": "AccessTokenError"
            })

        url = "https://api-m.sandbox.paypal.com/v1/billing/plans"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "product_id": product_id,
            "name": "Weekly Donation Plan",
            "description": "A plan for weekly donations.",
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": "WEEK",
                        "interval_count": 1
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": f"{amount:.2f}",
                            "currency_code": "USD"
                        }
                    }
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "setup_fee": {
                    "value": "0.00",
                    "currency_code": "USD"
                },
                "setup_fee_failure_action": "CONTINUE",
                "payment_failure_threshold": 3
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 201:
            plan_id = response.json().get("id")
            if not plan_id:
                logger.error("PayPal plan created, but no plan ID returned.")
                return cors_response(500, {
                    "message": "Plan creation succeeded, but the response is incomplete.",
                    "errorType": "IncompleteResponse"
                })
            return plan_id
        else:
            error_details = response.json()
            logger.error(f"PayPal Plan Creation Failed: {error_details}")
            return cors_response(response.status_code, {
                "message": f"Failed to create PayPal plan: {error_details.get('name', 'Unknown error')} - {error_details.get('message', 'No description')}.",
                "errorType": "PayPalAPIError",
                "details": error_details
            })
    except requests.exceptions.Timeout:
        logger.error("PayPal API request timed out.")
        return cors_response(504, {
            "message": "The request to the PayPal API timed out. Please try again later.",
            "errorType": "TimeoutError"
        })
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while connecting to PayPal API.")
        return cors_response(503, {
            "message": "Unable to connect to the PayPal API. Please check your network and try again.",
            "errorType": "ConnectionError"
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"Unhandled request exception: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while connecting to the PayPal API.",
            "errorType": "RequestError"
        })
    except Exception as e:
        logger.error(f"Unexpected error in create_paypal_plan: {e}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while creating the PayPal plan. Please try again later.",
            "errorType": "InternalError"
        })

# Create Paypal Subscription
def create_paypal_subscription(plan_id, custom_id):
    try:
        if not plan_id:
            logger.error("Plan ID is required to create a PayPal subscription.")
            return cors_response(400, {
                "message": "Plan ID is required to create a PayPal subscription.",
                "errorType": "ValidationError"
            })

        if not custom_id:
            logger.error("Custom ID is required to create a PayPal subscription.")
            return cors_response(400, {
                "message": "Custom ID is required to create a PayPal subscription.",
                "errorType": "ValidationError"
            })

        access_token = get_paypal_access_token()
        if not access_token:
            logger.error("Failed to retrieve PayPal access token.")
            return cors_response(500, {
                "message": "Failed to retrieve PayPal access token.",
                "errorType": "AccessTokenError"
            })

        url = "https://api-m.sandbox.paypal.com/v1/billing/subscriptions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        payload = {
            "plan_id": plan_id,
            "custom_id": custom_id
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 201:
            subscription = response.json()
            return cors_response(201, {
                "subscription": subscription
            })
        else:
            error_details = response.json()
            logger.error(f"PayPal subscription creation failed: {error_details}")
            return cors_response(response.status_code, {
                "message": f"Failed to create PayPal subscription: {error_details.get('name', 'Unknown error')} - {error_details.get('message', 'No description')}.",
                "errorType": "PayPalAPIError",
                "details": error_details
            })
    except requests.exceptions.Timeout:
        logger.error("PayPal API request timed out.")
        return cors_response(504, {
            "message": "The request to the PayPal API timed out. Please try again later.",
            "errorType": "TimeoutError"
        })
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while connecting to PayPal API.")
        return cors_response(503, {
            "message": "Unable to connect to the PayPal API. Please check your network and try again.",
            "errorType": "ConnectionError"
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"Unhandled request exception: {e}")
        return cors_response(500, {
            "message": "An unexpected error occurred while connecting to the PayPal API.",
            "errorType": "RequestError"
        })
    except Exception as e:
        logger.error(f"Unexpected error in create_paypal_subscription: {e}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while creating the PayPal subscription. Please try again later.",
            "errorType": "InternalError"
        })

# Create Paypal Subscription route
def create_paypal_subscription_route(amount, custom_id):
    try:
        if amount <= 0:
            logger.error("Amount must be greater than zero.")
            return cors_response(400, {
                "message": "Amount must be greater than zero.",
                "errorType": "ValidationError"
            })

        if not custom_id or not custom_id.strip():
            logger.error("Custom ID must be a non-empty string.")
            return cors_response(400, {
                "message": "Custom ID must be a non-empty string.",
                "errorType": "ValidationError"
            })

        product_id = create_paypal_product()
        if not product_id:
            logger.error("Failed to create PayPal product.")
            return cors_response(500, {
                "message": "Failed to create PayPal product.",
                "errorType": "ProductCreationError"
            })

        plan_id = create_paypal_plan(product_id, amount)
        if not plan_id:
            logger.error("Failed to create PayPal plan.")
            return cors_response(500, {
                "message": "Failed to create PayPal plan.",
                "errorType": "PlanCreationError"
            })

        subscription = create_paypal_subscription(plan_id, custom_id)
        subscription_id = subscription.get("id")
        if not subscription_id:
            logger.error("Subscription ID is missing from the PayPal response.")
            return cors_response(500, {
                "message": "Subscription ID is missing from the PayPal response.",
                "errorType": "IncompleteResponse"
            })

        approval_url = next(
            (link["href"] for link in subscription.get("links", []) if link["rel"] == "approve"),
            None
        )
        if not approval_url:
            logger.error("Approval URL is missing from the PayPal response.")
            return cors_response(500, {
                "message": "Approval URL is missing from the PayPal response.",
                "errorType": "IncompleteResponse"
            })

        return cors_response(200, {
            "subscription_id": subscription_id,
            "approval_url": approval_url,
            "message": "PayPal subscription created successfully."
        })

    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        return cors_response(400, {
            "message": str(ve),
            "errorType": "ValidationError"
        })
    except Exception as e:
        logger.error(f"Unexpected error creating PayPal subscription: {str(e)}", exc_info=True)
        return cors_response(500, {
            "message": "An unexpected error occurred while processing your request. Please try again later.",
            "errorType": "InternalError"
        })
