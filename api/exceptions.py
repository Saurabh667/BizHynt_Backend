from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        message = ''
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                message = str(response.data['detail'])
            elif 'message' in response.data:
                message = str(response.data['message'])
            else:
                first_val = next(iter(response.data.values()), '')
                if isinstance(first_val, list) and len(first_val) > 0:
                    message = str(first_val[0])
                else:
                    message = str(first_val)
        elif isinstance(response.data, list) and len(response.data) > 0:
            message = str(response.data[0])
        else:
            message = str(response.data)

        response.data = {
            'success': False,
            'statusCode': response.status_code,
            'message': message or 'An error occurred.',
            'error': response.data
        }

    return response
