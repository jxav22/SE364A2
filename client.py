from collections import OrderedDict
import socket
import sys
import argparse
import json
import threading


class LoginView:
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        username = input("username: ")
        password = input("password: ")

        response = client_controller.login(username, password)

        if response["status"] == "success":
            client_controller.record_logged_in_user(username, password)
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
    def __init__(self, client_controller):
        self.client_controller = client_controller

    def activate(self):
        response = client_controller.advertise()

        if response["status"] == "success":
            options = ChatOptions(client_controller, response["users"])

            if len(options.get_options()) == 0:
                print("No users online\nTry Again?")
                selected = int(input("[0] Yes\n[1] No\n>"))
                if selected == 0:
                    self.activate()
            else:
                while True:
                    print("Select a user to chat with:")
                    for index, key in enumerate(options.get_options()):
                        print(f"[{index}] {key}")
                    selected = int(input(">"))
                    options.select_option(selected)
        elif response["status"] == "failure":
            print(response["message"])


class HomeView:
    def __init__(self, client_controller):
        self.client_controller = client_controller
        self.options = HomeOptions(client_controller)

    def activate(self):
        while True:
            if client_controller.is_logged_in:
                print(f"Logged in as [{client_controller.username}]")

            print("Select an action:")
            for index, key in enumerate(self.options.get_options()):
                print(f"[{index}] {key}")
            selected = int(input(">"))
            self.options.select_option(selected)

class MessageView:
    def __init__(self, client_controller):
        self.client_controller = client_controller
    
    def activate(self):
        print("Type \quit to exit")
        while True:
            message = input("")
            if message == "\quit":
                break
            else:
                print(f"{client_controller.username}: {message}")
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
                response = client_controller.connect(user)
                if response["status"] == "success":
                    print(f"Connected to {user}")
                    MessageView(self.client_controller).activate()

            self.add_option(user, connect)


class ClientController:
    username = None
    password = None

    is_logged_in = False

    def __init__(self, client):
        self.request_helper = RequestHelper(client)

    def record_logged_in_user(self, username, password):
        self.username = username
        self.password = password
        self.is_logged_in = True

    def login(self, username, password):
        data = {"command": "login", "username": username, "password": password}
        return self.request_helper.request(data)

    def register(self, username, password):
        data = {"command": "register", "username": username, "password": password}
        return self.request_helper.request(data)

    def advertise(self):
        data = {
            "command": "advertise",
            "username": self.username,
            "password": self.password,
        }
        return self.request_helper.request(data)

    def connect(self, username):
        data = {
            "command": "connect",
            "username": self.username,
            "password": self.password,
            "target": username,
        }
        return self.request_helper.request(data)
    
    def send(self, message):
        data = {
            "command": "message",
            "username": self.username,
            "password": self.password,
            "message": message,
        }
        return self.request_helper.request(data)

class RequestHelper():
    timeout = 60
    id = 0

    def __init__(self, client):
        self.client = client
        self.event_pool = {}

        threading.Thread(target=self.listen).start()

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
        while True:
            response = self.client.receive()
            if response.get("ID") in self.event_pool:
                event = self.event_pool[response["ID"]]

                self.event_pool[response["ID"]] = response

                event.set()
            elif response.get("command") == "message":
                print(f"{response['username']}: {response['message']}")
            else:
                print(response)
    

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
        except socket.error as e:
            print(f"Socket error: {str(e)}")
        except Exception as e:
            print(f"Other exception: {str(e)}")
    
    def receive(self):
        response_data = self.client_socket.recv(self.buffer_size)
        return self.process_received(response_data)

    def close(self):
        print("Closing connection to the server")
        self.client_socket.close()


if __name__ == "__main__":
    client = Client("localhost", 20)
    client.start()
    
    client_controller = ClientController(client)

    home_view = HomeView(client_controller)
    home_view.activate()
