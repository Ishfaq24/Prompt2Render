---
title: How GitHub SSH Keys and Authentication Work
topic: Understanding asymmetric public-private key cryptography, the SSH handshake, and secure git operations
audience: undergraduate computer science and software engineers
---

## 1 - Asymmetric Key Pairs: Public vs Private
> ANIM: Use SplitStage showing a private key on the left labeled "id_ed25519" (Secret) and a public key on the right labeled "id_ed25519.pub" (Shared with GitHub). Highlight that the private key never leaves the client's laptop.

When you authenticate with GitHub using SSH, you rely on asymmetric cryptography. Instead of sending a plaintext password over the network, your machine generates a mathematically linked key pair: a private key that stays securely stored on your laptop, and a public key that you safely upload to your GitHub profile settings.

## 2 - The Cryptographic Challenge Handshake
> ANIM: Use FlowStage connecting the local developer laptop to the GitHub SSH Server. Show GitHub sending a random 256-bit challenge string to the laptop, the client signing the challenge with the private key, and GitHub verifying the signature with the public key.

When you execute git push, GitHub initiates a cryptographic challenge. GitHub sends a random string of bytes known as a nonce. Your local SSH client signs the challenge using your private key. GitHub then verifies the signature using your public key. If the signature is valid for the original nonce, GitHub instantly confirms your identity without ever seeing your private key.

## 3 - Client SSH Configuration and Multiplexing
> ANIM: Use SplitStage displaying a TerminalCard on the left with ~/.ssh/config rules and a ServerNode on the right routing multiple identity files to personal versus enterprise repositories.

To manage multiple keys, software engineers use the SSH configuration file. By specifying host aliases, key locations, and multiplexing sockets, your SSH agent automatically presents the correct key for personal projects versus enterprise organizations, all while maintaining end-to-end encrypted transport over port 22.

## 4 - Summary: Trust Without Shared Secrets
> ANIM: Use HeroFocusStage centering an end-to-end secure Git tunnel between Developer and GitHub, decorated with badges for "Ed25519 Curve", "Zero Secret Leakage", and "Automated CI/CD".

In summary, SSH authentication eliminates the risks of password theft and replay attacks. By combining public-key verification, ephemeral session encryption, and local key agents, SSH provides the foundational trust layer that powers modern distributed version control.

