import connexion
from openapi_server.db_models import Webhook
from mongoengine.errors import ValidationError

def create_webhook():
    """API để client đăng ký nhận thông báo"""
    if connexion.request.is_json:
        body = connexion.request.get_json()
        try:
            webhook = Webhook(
                url=body['url'],
                events=body['events']
            )
            webhook.save()
            return webhook.to_dict(), 201
        except ValidationError as e:
            return {'message': str(e)}, 400
        except Exception as e:
            return {'message': str(e)}, 500
    return 'Invalid input', 400