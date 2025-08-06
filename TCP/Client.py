import socket


DEST_IP = socket.gethostbyname(socket.gethostname())
DEST_PORT = 12345
ENCODER = 'utf-8'
BYTESIZE = 1024

client_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

client_socket.connect((socket.gethostbyname(socket.gethostname()),12345))
message = client_socket.recv(BYTESIZE)

client_socket.close()

print(message.decode(ENCODER))

