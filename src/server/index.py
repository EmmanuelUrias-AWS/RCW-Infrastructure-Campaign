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
ssm = boto3.client('ssm')

environment = os.getenv('ENVIRONMENT')
domain_name = os.getenv('DOMAIN_NAME')

def get_ssm_parameter(name: str) -> str:
    """Fetch a parameter from AWS SSM Parameter Store with decryption enabled."""
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response['Parameter']['Value']

def get_environment() -> str:
    """Retrieve the deployment environment, defaulting to 'dev' if not set."""
    return os.environ.get("ENVIRONMENT", "dev")

def get_user_pool_id() -> str:
    """Retrieve Cognito User Pool ID from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/COGNITO_USER_POOL_ID")

def get_user_pool_client_id() -> str:
    """Retrieve Cognito User Pool Client ID from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/COGNITO_CLIENT_ID")

def get_paypal_client_id() -> str:
    """Retrieve PayPal Client ID from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/PAYPAL_CLIENT_ID")

def get_paypal_secret() -> str:
    """Retrieve PayPal Secret from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/PAYPAL_SECRET")

def get_sender_email() -> str:
    """Retrieve SES Sender Email from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/SESIdentitySenderParameter")

def get_recipient_email() -> str:
    """Retrieve SES Recipient Email from SSM."""
    return get_ssm_parameter(f"/rcw-client-backend-{get_environment()}/SESRecipientParameter")

# ALLOW_ORIGIN = domain_name

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    try:
        # Extract HTTP method and resource path from the event
        http_method = event['httpMethod']
        resource_path = event['path']
        
        # Handle OPTIONS preflight request upfront to avoid multiple checks
        if http_method == "OPTIONS":
            return cors_response(200, {"message": "CORS preflight successful"})
        
        # Parse body for non-GET/DELETE requests
        if http_method not in ['GET', 'DELETE']:
            body = json.loads(event.get('body', "{}"))
        
        # Extract common parameters from query or body
        email = body.get('email') if http_method not in ['GET', 'DELETE'] else event.get('queryStringParameters', {}).get('email')
        password = body.get('password') if http_method != 'GET' else None
        first_name = body.get('first_name') if http_method != 'GET' else None
        last_name = body.get('last_name') if http_method != 'GET' else None
        confirmation_code = body.get('confirmation_code') if http_method != 'GET' else None
        access_token = body.get('access_token') if http_method != 'GET' else None
        new_password = body.get('new_password') if http_method != 'GET' else None
        attribute_updates = body.get('attribute_updates', {}) if http_method != 'GET' else {}
        message = body.get('message') if http_method != 'GET' else None
        custom_id = body.get('custom_id') if http_method != 'GET' else None
        amount = body.get('amount') if http_method != 'GET' else None
        currency = body.get('currency', "USD") if http_method == "POST" and resource_path in ["/create-paypal-order", "/create-paypal-subscription"] else None
        
        # Route handler map
        route_map = {
            ("/signup", "POST"): lambda: sign_up(password, email, first_name, last_name),
            ("/confirm", "POST"): lambda: confirm_user(email),
            ("/confirm-email", "POST"): lambda: confirm_email(access_token, confirmation_code),
            ("/confirm-email-resend", "POST"): lambda: confirm_email_resend(access_token),
            ("/login", "POST"): lambda: log_in(email, password),
            ("/forgot-password", "POST"): lambda: forgot_password(email),
            ("/confirm-forgot-password", "POST"): lambda: confirm_forgot_password(email, confirmation_code, new_password),
            ("/user", "GET"): lambda: get_user(email),
            ("/user", "PATCH"): lambda: update_user(email, attribute_updates),
            ("/user", "DELETE"): lambda: delete_user(email),
            ("/contact-us", "POST"): lambda: contact_us(first_name, email, message),
            ("/create-paypal-order", "POST"): lambda: create_paypal_order_route(amount, custom_id, currency),
            ("/create-paypal-subscription", "POST"): lambda: create_paypal_subscription_route(amount, custom_id),
        }
        
        # Check if the route exists and execute the corresponding function
        result = route_map.get((resource_path, http_method))
        if result:
            return result()
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
            ClientId=get_user_pool_client_id(),
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
            UserPoolId=get_user_pool_id(),
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
            ClientId=get_user_pool_client_id(),
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
            ClientId=get_user_pool_client_id(),
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
            ClientId=get_user_pool_client_id(),
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
            UserPoolId=get_user_pool_id(),
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
            UserPoolId=get_user_pool_id(),
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
            UserPoolId=get_user_pool_id(),
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
            Source=get_sender_email(),
            Destination={'ToAddresses': [get_recipient_email()]},
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
    auth = (get_paypal_client_id(), get_paypal_secret())

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