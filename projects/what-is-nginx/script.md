---
title: What is NGINX and What Does It Do?
topic: How NGINX powers modern web infrastructure as a high-performance web server, reverse proxy, load balancer, and SSL terminator
audience: undergraduate computer science and software engineers
---

## 1 - The Web Server That Solved the C10K Problem
> ANIM: On the left, draw client browsers requesting pages. In the center, draw a high-throughput NGINX event-driven engine labeled "NGINX CORE". On the right, draw cached static files (HTML, CSS, IMAGES) and a database icon "storage_db". Show NGINX serving static files instantly without spawning new processes.

Early web servers like Apache spawned a separate operating system thread or process for every single visitor. When thousands of users connected at the same time, servers ran out of memory and collapsed — a challenge known as the C10K problem. NGINX solved this by using an asynchronous, event-driven architecture. A single master process with a handful of worker processes can handle tens of thousands of simultaneous HTTP connections on modest hardware without breaking a sweat.

## 2 - The Reverse Proxy: Shielding Your Backend
> ANIM: On the left, show incoming traffic from the public internet. In the center, place an NGINX box acting as a reverse proxy gateway labeled "REVERSE PROXY". On the right, show internal private application servers labeled App 1, App 2, and App 3 behind a secure firewall boundary. Draw arrows showing requests flowing through NGINX to private ports.

A traditional proxy helps clients access the internet, but a reverse proxy does the exact opposite: it sits in front of backend servers and intercepts requests from clients. When you request a URL, you never talk to the Python, Node.js, or Java application directly. NGINX receives the request, enforces rate limits, sanitizes headers, and securely forwards the traffic to the private application servers running behind the firewall.

## 3 - Load Balancing with Upstream Configuration
> ANIM: Display a clean NGINX configuration block showing `upstream backend_cluster` with `server app1:8080` and `server app2:8080`, followed by `location / { proxy_pass http://backend_cluster; }`. Next to it, animate incoming HTTP requests being distributed round-robin between App 1 and App 2.

When traffic spikes, a single application server cannot keep up. In NGINX, you configure load balancing by defining an upstream pool: `upstream backend_cluster`, listing your private server addresses, and pointing incoming routes to that pool using `proxy_pass`. NGINX distributes requests across those nodes using algorithms like Round Robin, Least Connections, or IP Hash. It also performs passive health checks, instantly rerouting traffic if a backend node fails.

## 4 - SSL Termination and Edge Caching
> ANIM: On the left, show encrypted "HTTPS / TLS" client traffic reaching NGINX. Show NGINX decrypting the traffic at the edge ("SSL TERMINATION") and forwarding requests to private application servers. Below, show an "EDGE CACHE" box storing responses and returning them instantly.

Handling cryptographic handshakes for HTTPS encryption is computationally expensive. NGINX performs SSL termination at the edge of your infrastructure, decrypting incoming TLS traffic and offloading that cryptographic burden from your application servers. It also caches dynamic responses in memory or disk. When another user requests the same data, NGINX serves it directly from the cache in sub-milliseconds without touching your backend database at all.

## 5 - Summary: The Swiss Army Knife of Modern Web Architecture
> ANIM: Draw a central NGINX block connecting the public Internet on the left to an internal application cluster and database on the right. Highlight four corner badges representing its core superpowers: "Event-Driven C10K", "Reverse Proxy", "Load Balancer", and "SSL / Cache Edge".

In summary, NGINX acts as the high-performance entry point for modern web architectures. By replacing thread-per-connection concurrency with an asynchronous event loop, it efficiently manages reverse proxying, load balancing, SSL termination, and edge caching — shielding your backend application servers from the bottleneck of the C10K problem.