#!/usr/bin/env python3

"""
Example of a command connection to send arbitrary commands to the machine

Make sure when running this script to have access to the DSF UNIX socket owned by the dsf user.
"""

from dsf.connections import CommandConnection

from dsf.connections import SubscribeConnection, SubscriptionMode

def send_simple_code(code):

   connection = CommandConnection()
   connection.connect()
   try:
       response = connection.perform_simple_code(str(code))
       print(f'{response}')
   except Exception as e:
       print(f'Error: {e}')
   finally:
       connection.close()


def subscribe():
    subscribe_connection = SubscribeConnection(SubscriptionMode.PATCH)
    subscribe_connection.connect()

    # Get the complete model once
    object_model = subscribe_connection.get_object_model()
    print(object_model)

    # Get multiple incremental updates, due to SubscriptionMode.PATCH, only a
    # subset of the object model will be updated
    for _ in range(0, 3):
        update = subscribe_connection.get_object_model_patch()
        object_model.update_from_json(update)
        print(update)
    subscribe_connection.close()


if __name__ == "__main__":
    send_simple_code("M122 DSF")
    # subscribe()