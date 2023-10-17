from collections import OrderedDict
import socket
import sys
import argparse
import json


class LoginView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        success = False
        while not success:
            username = input("username: ")
            password = input("password: ")

            response = client_controller.login(username, password)

            if response["status"] == "success":
                client_controller.record_logged_in_user(username, password)
                success = True
            else:
                print("Invalid username or password")
                break


class RegisterView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        success = False
        while not success:
            username = input("username: ")
            password = input("password: ")

            response = client_controller.register(username, password)

            if response["status"] == "success":
                print("Successfully registered user")
                success = True
            else:
                print("Failed to register user")
                break


class ChatView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        response = client_controller.advertise()

        if response["status"] == "success":
            options = ChatOptions(client_controller, response["users"])

            if len(options.get_options()) == 0:
                print("No users to chat with\nTry Again?")
                selected = int(input("[0] Yes\n[1] No\n>"))
                if selected == 0:
                    self.activate()
            else:
                while True:
                    for index, key in enumerate(options.get_options()):
                        print(f"[{index}] {key}")
                    selected = int(input(">"))
                    self.options.select_option(selected)
        else:
            print("You cannot do this")


class HomeView:
    def __init__(self, client_controller):
        self.client_controller = client_controller
        self.options = HomeOptions(client_controller)

    def activate(self):
        while True:
            if client_controller.is_logged_in:
                print(f"Logged in as [{client_controller.username}]", end='\n\n')

            print("Select an action:")
            for index, key in enumerate(self.options.get_options()):
                print(f"[{index}] {key}")
            selected = int(input(">"))
            self.options.select_option(selected)

class MessageView:
    def __init__(self, client_controller):
        self.client_controller = client_controller
    
    def activate(self):
        while True:
            message = int(input(">"))
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


class HomeOptions(Options):
    options = OrderedDict()

    def login(self):
        LoginView(self.client_controller).activate()

    def register(self):
        RegisterView(self.client_controller).activate()

    def chat(self):
        ChatView(self.client_controller).activate()

    def __init__(self, client_controller):
        self.client_controller = client_controller

        self.add_option("Login", self.login)
        self.add_option("Register", self.register)
        self.add_option("Chat", self.chat)


class ChatOptions(Options):
    options = OrderedDict()

    def __init__(self, client_controller, users):
        self.client_controller = client_controller
        self.users = users

        for user in self.users:
            def connect():
                client_controller.connect(user)

            self.add_option(user, connect)


class ClientController:
    username = None
    password = None

    is_logged_in = False

    def __init__(self, client):
        self.client = client

    def record_logged_in_user(self, username, password):
        self.username = username
        self.password = password
        self.is_logged_in = True

    def login(self, username, password):
        data = {"command": "login", "username": username, "password": password}
        return self.client.send(data)

    def register(self, username, password):
        data = {"command": "register", "username": username, "password": password}
        return self.client.send(data)

    def advertise(self):
        data = {
            "command": "advertise",
            "username": self.username,
            "password": self.password,
        }
        return self.client.send(data)

    def connect(self, username):
        data = {
            "command": "connect",
            "username": self.username,
            "password": self.password,
            "target": username,
        }
        return self.client.send(data)


class Client:
    buffer_size = 2048

    def __init__(self, host, port):
        self.host = host
        self.port = port

        # Create a TCP/IP socket
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
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
            response_data = self.client_socket.recv(self.buffer_size)
            return self.process_received(response_data)
        except socket.error as e:
            print(f"Socket error: {str(e)}")
        except Exception as e:
            print(f"Other exception: {str(e)}")

    def close(self):
        print("Closing connection to the server")
        self.client_socket.close()


if __name__ == "__main__":
    client = Client("localhost", 20)
    client_controller = ClientController(client)
    client.start()

    home_view = HomeView(client_controller)
    home_view.activate()
