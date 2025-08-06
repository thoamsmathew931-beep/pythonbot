import socket


HOST_IP = socket.gethostbyname(socket.gethostname())
HOST_PORT = 12345
ENCODER = 'utf-8'
BYTESIZE = 1024

server_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

server_socket.bind((HOST_IP,HOST_PORT))

server_socket.listen()



while True:
    client_socket, client_address = server_socket.accept()
    print('received connection from %s' % str(client_address))

    message = 'hello thank you for connecting to the server'+ '\r\n'
    client_socket.send(message.encode(ENCODER))

    client_socket.close()
