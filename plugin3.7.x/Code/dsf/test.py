#!/usr/bin/env python3

"""
Example of a command connection to send arbitrary commands to the machine

Make sure when running this script to have access to the DSF UNIX socket owned by the dsf user.
"""

from dsf.connections import CommandConnection

from dsf.connections import SubscribeConnection, SubscriptionMode

import time

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


def get_complete_om():
    try:
        subscribe_connection = SubscribeConnection(SubscriptionMode.PATCH)
        subscribe_connection.connect()
        # Get the complete model once
        om = subscribe_connection.get_object_model()
    except Exception as e:
        print(f'Error: {e}')
        om = False
    finally:
        #subscribe_connection.close()
        return om , subscribe_connection

def update_om(om, subscribe_connection):
    # Get incremental update, due to SubscriptionMode.PATCH, only a
    # subset of the object model will be updated
    try:
        #subscribe_connection = SubscribeConnection(SubscriptionMode.PATCH)
        #subscribe_connection.connect()
        update = subscribe_connection.get_object_model_patch()
        print('Update -------------------')
        print(update)
        print('---------------------------')
        om.update_from_json(update)
    except Exception as e:
        print(f'Error: {e}')
        update = False
    finally:
        #subscribe_connection.close()
        return om

if __name__ == "__main__":
    #send_simple_code("M122 DSF")
    object_model, connection = get_complete_om()
    time.sleep(10)
    object_model = update_om(object_model, connection)
    print(object_model)
    connection.close()