---
title: How the Internet Works: Packets, DNS, and Routers
topic: How data travels across the global internet from client requests to server responses
audience: undergraduate computer science
---

## 1 - Clients and Servers
> ANIM: On the left, draw a client computer labeled "CLIENT". On the right, draw a server box labeled "SERVER" with a database icon "storage_db". Show a bidirectional arrow connecting them labeled "REQUEST / RESPONSE".

When you open a website, your computer acts as a client. It sends a request across the network asking for a specific webpage, video, or data file. Somewhere across the globe, a server listening on the network receives your request, retrieves the requested resource from its storage or database, and streams the response data right back to your screen.

## 2 - DNS: The Phonebook of the Internet
> ANIM: Draw the client querying a "DNS RESOLVER" server with domain "example.com". The DNS server replies with IP address "93.184.216.34". An arrow then routes directly from client to the target server at that IP.

Computers do not communicate using human-readable domain names like example.com. They communicate using numerical IP addresses. When you type a web address, your client first queries the Domain Name System, or DNS. The DNS acts like the phonebook of the internet, resolving the human domain name into the exact destination IP address where the server lives.

## 3 - Packets and Routers
> ANIM: Break a message into three numbered data packets labeled P1, P2, and P3. Draw a network mesh of three intermediate "ROUTER" nodes. Show each packet hopping independently across the mesh before reassembling in order at the destination.

Large files are never transmitted as one single piece. Instead, the internet protocol splits every message into small, numbered packets. Specialized network switches called routers read each packet's destination header and forward it along the fastest available path. Even if packets take different routes, the receiving machine reassembles them in exact sequence.