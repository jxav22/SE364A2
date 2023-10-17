from collections import OrderedDict
import socket
import sys
import argparse
import json
import threading

from client_server import ContextSwitcher as ClientServerContextSwitcher

class LoginView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        username = input("username: ")
        password = input("password: ")

        response = client_controller.login(username, password)

        if response["status"] == "success":
            client_controller.record_credentials(username, password)
        elif response["status"] == "failure":
            print(response["message"])


class RegisterView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        username = input("username: ")
        password = input("password: ")

        response = client_controller.register(username, password)

        if response["status"] == "success":
            print("Successfully registered user")
        elif response["status"] == "failure":
            print(response["message"])


class ChatView:
    def __init__(self, client_controller, view_manager):
        self.client_controller = client_controller
        self.view_manager = view_manager

    def activate(self):
        response = client_controller.advertise()

        if response["status"] == "success":
            options = ChatOptions(client_controller, self.view_manager, response["users"])

            if len(options.get_options()) == 0:
                print("No users online\nTry Again?")
                selected = int(input("[0] Yes\n[1] No\n>"))
                if selected == 0:
                    self.activate()
            else:
                while self.view_manager.active:
                    print("Select a user to chat with:")
                    options.display()
                    selected = int(input(">"))
                    options.select_option(selected)
        elif response["status"] == "failure":
            print(response["message"])


class HomeView:
    def __init__(self, client_controller, view_manager):
        self.client_controller = client_controller
        self.options = HomeOptions(client_controller, view_manager)
        self.view_manager = view_manager

    def activate(self):
        while self.view_manager.active:
            if client_controller.user_data.is_logged_in:
                print(f"Logged in as [{client_controller.user_data.username}]")

            print("Select an action:")
            self.options.display()
            selected = int(input(">"))
            self.options.select_option(selected)
            self.view_manager.reset()

class MessageView:
    def __init__(self, client_controller, view_manager):
        self.client_controller = client_controller
        self.view_manager = view_manager
    
    def activate(self):
        print("Type quit to exit")
        while self.view_manager.active:
            message = input("")
            if message == "quit":
                self.client_controller.quit()
                self.view_manager.restart()
                break
            else:
                print(f"{client_controller.user_data.username}: {message}")
                client_controller.send(message)

class Options:
    def add_option(self, key, value):
        self.options[key] = value

    def get_options(self):
        return list(self.options.keys())

    def select_option(self, index):
        if self.is_valid_index(index):
            options_items = list(self.options.items())
            return options_items[index][1]()

    def is_valid_index(self, index):
        return index < len(self.options) and index >= 0
    
    def display(self):
        for index, key in enumerate(self.get_options()):
            print(f"[{index}] {key}")


class HomeOptions(Options):
    options = OrderedDict()

    def login(self):
        LoginView(self.client_controller).activate()

    def register(self):
        RegisterView(self.client_controller).activate()

    def chat(self):
        ChatView(self.client_controller, self.view_manager).activate()

    def __init__(self, client_controller, view_manager):
        self.client_controller = client_controller
        self.view_manager = view_manager

        self.add_option("Login", self.login)
        self.add_option("Register", self.register)
        self.add_option("Chat", self.chat)


class ChatOptions(Options):
    options = OrderedDict()

    def __init__(self, client_controller, view_manager, users):
        self.client_controller = client_controller
        self.view_manager = view_manager
        self.users = users

        for user in self.users:
            context_switcher = ContextSwitcher(client_controller, view_manager, user)
            self.add_option(user, context_switcher.connect)

class ContextSwitcher:
    def __init__(self, client_controller, view_manager, user):
        self.client_controller = client_controller
        self.view_manager = view_manager
        self.user = user

    def extract_data(self, response):
        self.username = response.get("username")
        self.is_client = response.get("is_client")
        self.address = response.get("address")
        self.port = response.get("port")

    def switch_context(self):
        self.client_controller.stop()
        ClientServerContextSwitcher(self.address, self.port, self.username, self.is_client)
        self.view_manager.restart()
        self.client_controller.start()

    def connect(self):
        print(f"Connecting to {self.user}...")
        response = client_controller.connect(self.user)
        if response["status"] == "success":
            print(f"Connected to {self.user}")
            self.extract_data(response)
            self.switch_context()

class UserData:
    def __init__(self):
        self.username = None
        self.password = None
        self.is_logged_in = False
    
    def store_credentials(self, username, password):
        self.username = username
        self.password = password
        self.is_logged_in = True

class ClientController:
    def __init__(self, client):
        self.client = client
        self.request_helper = RequestHelper(client)

        self.user_data = UserData()

    def record_credentials(self, username, password):
        self.user_data.store_credentials(username, password)

    def stop(self):
        self.request_helper.stop()
        self.client.close()

    def start(self):
        self.user_data = UserData()
        self.client.start()
        self.request_helper = RequestHelper(client)

    def login(self, username, password):
        data = {"command": "login", "username": username, "password": password}
        return self.request_helper.request(data)

    def register(self, username, password):
        data = {"command": "register", "username": username, "password": password}
        return self.request_helper.request(data)

    def advertise(self):
        data = {
            "command": "advertise",
            "username": self.user_data.username,
            "password": self.user_data.password,
        }
        return self.request_helper.request(data)

    def connect(self, username):
        data = {
            "command": "connect",
            "username": self.user_data.username,
            "password": self.user_data.password,
            "target": username,
        }
        return self.request_helper.request(data)
    
    def send(self, message):
        data = {
            "command": "message",
            "username": self.user_data.username,
            "password": self.user_data.password,
            "message": message,
        }
        return self.request_helper.request(data)
    
    def quit(self):
        data = {
            "command": "message",
            "username": self.user_data.username,
            "password": self.user_data.password,
            "message": "",
            "quit": True
        }
        return self.request_helper.request(data)

class RequestHelper():
    timeout = 60
    id = 0

    def __init__(self, client):
        self.client = client
        self.event_pool = {}

        self.stop_event = threading.Event()
        self.start()

    def request(self, data):
        self.id += 1
        data["ID"] = self.id
        self.client.send(data)

        self.event_pool[self.id] = threading.Event()
        flag = self.event_pool[self.id].wait(self.timeout)

        if flag:
            return self.event_pool[self.id]
        else:
            return {"status": "failure", "message": "Request timed out"}
    
    def listen(self):
        while not self.stop_event.is_set():
            response = self.client.receive()
            if response.get("ID") in self.event_pool:
                event = self.event_pool[response["ID"]]

                self.event_pool[response["ID"]] = response

                event.set()
            else:
                print(response)

    def stop(self):
        self.stop_event.set()

    def start(self):
        self.stop_event.clear()
        threading.Thread(target=self.listen).start()
    

class Client:
    buffer_size = 2048

    def __init__(self, host, port):
        self.host = host
        self.port = port

    def start(self):
        # Create a TCP/IP socket
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Connect the socket to the server
        self.client_socket.connect((self.host, self.port))
        print(f"Client started on {self.host}:{self.port}...")

    def process_before_sending(self, data):
        return json.dumps(data).encode("utf-8")

    def process_received(self, data):
        return json.loads(data.decode())

    def send(self, data):
        try:
            self.client_socket.sendall(self.process_before_sending(data))
        except socket.error as e:
            print(f"Socket error: {str(e)}")
        except Exception as e:
            print(f"Other exception: {str(e)}")
    
    def receive(self):
        try:
            response_data = self.client_socket.recv(self.buffer_size)
            return self.process_received(response_data)
        except Exception as e:
            print(f"Other exception: {str(e)}")
            return {"status": "failure", "message": "Error receiving data"}

    def close(self):
        print("Closing connection to the server")
        self.client_socket.close()

class ViewManager:
    def __init__(self):
        self.active = True
        self.reset_flag = False
    
    def restart(self):
        self.active = False
        self.reset_flag = True

    def reset(self):
        if self.reset_flag:
            self.active = True

if __name__ == "__main__":
    client = Client("localhost", 20)
    client.start()
    
    client_controller = ClientController(client)

    view_manager = ViewManager()

    home_view = HomeView(client_controller, view_manager)
    home_view.activate()
