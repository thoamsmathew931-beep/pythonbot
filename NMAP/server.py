import nmap

scanner = nmap.PortScanner()

print('Welcome, this is a simple nmap automation tool')
print('<----------------------------------------------------------->')
ip_addr = input('Please enter ip address you want to scan: ')
print('The ip you entered is: ',ip_addr)