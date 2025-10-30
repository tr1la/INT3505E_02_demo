#!/usr/bin/env python3

import connexion
from mongoengine import connect
from openapi_server import encoder


def main():
    connect('product_db', host='mongodb+srv://tr1la:chuviblachuoi@mymongo.teuyzcm.mongodb.net/?appName=MyMongo') 
    print("Kết nối MongoDB thành công!")
    app = connexion.App(__name__, specification_dir='./openapi/')
    app.app.json_encoder = encoder.JSONEncoder
    app.add_api('openapi.yaml',
                arguments={'title': 'Product API'},
                pythonic_params=True)

    app.run(port=8080)


if __name__ == '__main__':
    main()
