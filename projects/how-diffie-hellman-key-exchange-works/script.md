---
title: Diffie-Hellman Key Exchange: Math and Mechanics
topic: Diffie-Hellman key exchange, symmetric key distribution problem, modular exponentiation, discrete logarithm problem, computational Diffie-Hellman assumption, man-in-the-middle vulnerability
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~15 min total = ~2100 words
     across 9 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - The Key Exchange Dilemma
> ANIM: Show Alice and Bob attempting to send encrypted messages over an open network, while Eve sniffs every packet passing through.

How do two parties who have never met establish a shared secret key over a channel where an adversary listens to every single byte? This is the fundamental dilemma of symmetric key cryptography. If Alice and Bob want to use a fast algorithm like AES to secure their communication, they both need the exact same secret key. But if Alice simply generates a key and transmits it over an insecure network, an eavesdropper like Eve will capture that key instantly. Physical key delivery by trusted couriers does not scale for millions of internet connections established every second. To build secure protocols, we need a mathematical mechanism that allows Alice and Bob to construct a shared secret key in plain view of an adversary, without ever sending the secret itself over the wire.

## 2 - The Color Mixing Intuition
> ANIM: Animate paint buckets showing Alice and Bob mixing a shared public color with private secret colors, exchanging results, and arriving at identical secret mixtures.

Before diving into the underlying modular arithmetic, consider a physical analogy involving paint colors. Imagine Alice and Bob agree publicly on an initial starting color, like yellow. Eve knows this public color too. Now, Alice chooses a secret private color, say red, which she keeps entirely to herself. Bob also chooses a private color, like blue. Alice mixes her secret red paint into the public yellow paint to create a custom shade. Bob mixes his secret blue paint into the public yellow paint to create his own custom shade. 

They then exchange their mixed colors across the public channel. Eve captures both mixtures, but because unmixing paint to recover the original secret colors is practically impossible, she is stuck. Finally, Alice takes Bob's public mixture and adds her secret red paint to it. Bob takes Alice's public mixture and adds his secret blue paint to it. Because both individuals have combined the shared public yellow, Alice's secret red, and Bob's secret blue, they both arrive at the exact same final color mix. Eve, possessing only the starting color and the intermediate mixtures, cannot combine them to recreate that final secret shade.

## 3 - Setting Up Public Parameters: p=23 and g=5
> ANIM: Display the public parameter board showing prime modulus p=23 and base generator g=5 visible to Alice, Bob, and eavesdropper Eve.

To translate this intuition into public key cryptography, we replace paint mixing with operations in finite cyclic groups. The classic Diffie-Hellman protocol relies on two public parameters: a large prime number p, which serves as the modulus, and a generator g, which is a primitive root modulo p. Everyone on the network, including Alice, Bob, and Eve, has full access to these two numbers.

For our trace, we will use small numbers to observe the arithmetic directly. Let the public prime p equal twenty-three, and let the public base generator g equal five. The prime twenty-three defines our finite field, ensuring all intermediate calculation results stay bounded between zero and twenty-two. The base value five has the property that its powers modulo twenty-three generate a set of residue classes suitable for cryptographic operations. With p set to twenty-three and g set to five published openly, the parameter setup phase is complete.

## 4 - Alice Generates Her Public Value
> ANIM: Trace Alice selecting private secret a=4, computing public value A = 5^4 mod 23 = 4, and sending A=4 across the network to Bob.

With the public parameters established, Alice initiates her side of the key generation process. She selects a private integer, denoted as lower-case a, which she keeps strictly confidential. In our trace, Alice chooses a equal to four. This secret exponent acts as her private key.

Next, Alice computes her public value, denoted as upper-case A. She calculates g raised to the power of a modulo p. Substituting our established values, Alice computes five raised to the fourth power modulo twenty-three. Five raised to the fourth power equals six hundred twenty-five. When we divide six hundred twenty-five by twenty-three, the remainder is four. So Alice's public value A is four. Alice transmits this value A equal to four across the unsecure network to Bob. Eve captures this value of four as it passes over the wire, but she does not know Alice's secret exponent four.

## 5 - Bob Generates His Public Value
> ANIM: Trace Bob selecting private secret b=3, computing public value B = 5^3 mod 23 = 10, and sending B=10 across the network to Alice.

Concurrently or immediately after, Bob performs the complementary steps to generate his own public value. He selects his own private secret integer, denoted as lower-case b, keeping it entirely hidden from everyone else. In this trace, Bob chooses b equal to three.

Bob computes his public value, upper-case B, by raising the shared base g to his secret exponent b modulo p. Using our parameters, Bob evaluates five raised to the third power modulo twenty-three. Five raised to the third power is one hundred twenty-five. Dividing one hundred twenty-five by twenty-three yields a quotient of five with a remainder of ten. Therefore, Bob's public value B is ten. Bob sends B equal to ten over the network to Alice. Eve intercepts B equal to ten, adding it to her collection of observed public data alongside p equal to twenty-three, g equal to five, and A equal to four.

## 6 - Computing the Shared Secret
> ANIM: Show Alice computing 10^4 mod 23 = 18 and Bob computing 4^3 mod 23 = 18 simultaneously, highlighting the identical shared secret key S=18.

Now comes the critical step where both parties compute the shared secret without any further network communication. Alice has received Bob's public value B equal to ten, and she still holds her private secret exponent a equal to four. She computes the shared secret key S by raising Bob's public value B to her secret exponent a modulo p. That is ten raised to the fourth power modulo twenty-three. Ten raised to the fourth power is ten thousand. Dividing ten thousand by twenty-three leaves a remainder of eighteen.

Simultaneously, Bob takes Alice's public value A equal to four and raises it to his private exponent b equal to three modulo p. Four raised to the third power is sixty-four. Dividing sixty-four by twenty-three yields a remainder of eighteen. Alice and Bob have derived the exact same secret key S equal to eighteen. They can now use this integer eighteen to derive a symmetric encryption key for secure communication.

## 7 - Why the Math Works: Exponentiation Rules
> ANIM: Display algebraic substitution showing both calculations evaluate to (g^a)^b mod p = (g^b)^a mod p = g^(ab) mod p.

The mathematical guarantee that Alice and Bob compute the exact same value rests on basic exponentiation rules applied inside a finite group. Alice computed B raised to the power of a modulo p. But remember that B was originally derived as g raised to the power of b modulo p. Substituting Bob's formula into Alice's calculation shows that Alice actually computed the quantity g raised to the b, raised to the a, modulo p.

Similarly, Bob computed A raised to the power of b modulo p, where A was originally g raised to the power of a modulo p. Substituting Alice's formula into Bob's calculation shows that Bob evaluated the quantity g raised to the a, raised to the b, modulo p. By the algebraic power rule for exponents, raising a power to another exponent multiplies the exponents together. Therefore, g to the b to the a is algebraically equivalent to g to the a to the b, which both equal g raised to the product a times b modulo p. In our trace, five raised to the product of four and three modulo twenty-three equals five raised to the twelfth power modulo twenty-three, which evaluates precisely to eighteen.

## 8 - The Discrete Logarithm Hardness
> ANIM: Show Eve attempting to recover secret a from equation 5^a mod 23 = 4 using a brute-force search table across large prime modulus spaces.

The security of the Diffie-Hellman key exchange relies on an asymmetry in computational difficulty. Computing modular exponentiation is fast, but reversing it is computationally intractable when using real-world key sizes. An adversary like Eve observes the public prime p equal to twenty-three, the base g equal to five, Alice's public value A equal to four, and Bob's public value B equal to ten. To deduce Alice's secret exponent a, Eve must solve the equation five raised to the power of a modulo twenty-three equals four.

This task is known as the discrete logarithm problem. For small numbers like twenty-three, Eve can construct a table of powers and find that a equals four by brute force in a fraction of a millisecond. However, in real implementations, the prime p is thousands of bits long, typically two thousand forty-eight or four thousand ninety-six bits. In such massive finite fields, no efficient algorithm exists on classical computers to find the discrete logarithm. The computational Diffie-Hellman assumption posits that given g, g to the a, and g to the b, computing g to the a b is computationally infeasible without knowing either secret exponent a or b.

## 9 - The Man-in-the-Middle Attack
> ANIM: Animate Mallory intercepting public exchanges between Alice and Bob, establishing separate keys with each to highlight why authentication is needed next.

While the math of Diffie-Hellman prevents passive eavesdroppers from learning the secret key, the basic protocol is completely unauthenticated, making it vulnerable to an active attack. Suppose an adversary named Mallory sits directly in the communication path between Alice and Bob. When Alice sends her public value A equal to four, Mallory intercepts it and substitutes her own public value instead. Likewise, when Bob sends his public value B equal to ten, Mallory intercepts it and sends her own generated value to Alice.

Alice unwittingly computes a shared key with Mallory, thinking she is establishing it with Bob. Bob also computes a shared key with Mallory, thinking he is establishing it with Alice. From that point forward, Mallory can decrypt every message Alice sends, re-encrypt it, and forward it to Bob without either party noticing the interception. The fundamental mathematical mechanics of Diffie-Hellman successfully solve the problem of key agreement, but they do not prove identity. To prevent man-in-the-middle attacks, how can Alice and Bob cryptographically authenticate the public values they exchange?

