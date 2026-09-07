---
title: How DNS Works: The Internet's Phonebook
topic: How the Domain Name System translates human-readable domain names into IP addresses through recursive hierarchical resolution
audience: undergraduate computer science and software engineers
---

## 1 - The Need for Domain Name Resolution
> ANIM: Use SplitStage showing a user typing "example.com" into a browser on the left and a server with numeric IP "93.184.216.34" on the right.

Computers on the internet communicate using numeric IP addresses, but humans remember domain names. The Domain Name System, or DNS, bridges this gap by acting as a globally distributed, hierarchical database that translates human-friendly URLs into machine-routable IP addresses in milliseconds.

## 2 - The Recursive Resolution Chain
> ANIM: Use FlowStage connecting Browser -> Recursive Resolver -> Root DNS Server -> .com TLD Server -> Authoritative DNS Server with animated pulse signals traveling through the query chain.

When you request a website, your browser first asks a Recursive Resolver, usually provided by your ISP or cloud provider. If the IP is not in its local cache, the resolver initiates a top-down lookup: it queries the Root Name Server, which directs it to the Top-Level Domain server for dot-com, which in turn points to the Authoritative Name Server holding the actual zone records.

## 3 - Record Types and Caching Lifecycles
> ANIM: Use SplitStage displaying a ConfigCodeCard with DNS records (A, AAAA, CNAME, MX) on the left and a MetricBadge showing "TTL: 300s" on the right.

Authoritative servers return specific DNS record types: A records for IPv4, AAAA for IPv6, and CNAME for aliases. Every response includes a Time-To-Live, or TTL, instructing intermediate resolvers how many seconds to cache the result, preventing redundant cross-continental queries.

## 4 - Summary: The Backbone of Internet Navigation
> ANIM: Use HeroFocusStage centering a global DNS tree connected to badges for "Hierarchical Anycast", "Distributed Caching", and "DNSSEC Integrity".

In summary, DNS powers the speed, scalability, and resilience of the modern web. By combining hierarchical delegation, anycast routing, and aggressive edge caching, DNS ensures that billions of domain queries resolve reliably every single second.
