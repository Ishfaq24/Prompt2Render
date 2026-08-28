---
title: How Quantum Gates Manipulate State Vectors
topic: qubits, superposition, 2^n state vector space, Hadamard gate, CNOT gate, quantum interference, measurement collapse
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~2 min total = ~280 words
     across 4 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - The Exponential Limits of Classical Bits
> ANIM: A 3-bit classical register cycling sequentially through 8 binary states while a 3-qubit state vector tracks amplitudes across all 8 states simultaneously.

How can a quantum computer process information exponentially faster than a classical machine? The answer lies in how information is stored and tracked in hardware. A classical three-bit register can hold exactly one of eight possible binary configurations at any given moment, from zero-zero-zero to one-one-one. To evaluate all eight configurations, a classical algorithm must process each state one after another in sequence. In contrast, a three-qubit system stores its state as a single vector in an eight-dimensional vector space. Each of the eight basis states is assigned a complex number called a probability amplitude. Instead of occupying a single binary state, the three-qubit register maintains non-zero amplitudes across all eight configurations simultaneously. As a system scales to n qubits, a classical register still holds only one active state at a time, while the quantum state vector expands to two to the power of n simultaneous amplitudes.

## 2 - Representing Qubit Superposition with Vectors
> ANIM: A 2-qubit state vector listing four probability amplitudes initialized to the 00 basis state with unit magnitude.

To understand how quantum operations manipulate these state spaces, consider a two-qubit system. The state space of two qubits is spanned by four computational basis states: zero-zero, zero-one, one-zero, and one-one. We represent this complete state using a column vector containing four complex probability amplitudes. When we initialize the system to the zero-zero basis state, the amplitude for zero-zero is set to a magnitude of one, while the amplitudes for zero-one, one-zero, and one-one are all zero. The sum of the squared magnitudes of these four amplitudes must always sum to one to conserve total probability. Quantum superposition occurs whenever more than one amplitude in this four-element vector is non-zero. This allows the state vector to point in a direction that combines multiple computational basis states at the exact same time.

## 3 - Transforming Amplitudes with Quantum Gates
> ANIM: A 4x4 Hadamard-based unitary matrix multiplies the 2-qubit state vector to distribute amplitudes, followed by a CNOT gate swap operation.

Quantum gates modify superpositions by performing matrix multiplication directly on the state vector. Because quantum operations must preserve the total probability of the system, every valid gate is represented by a unitary matrix. Applying a Hadamard operation to the first qubit multiplies our four-element state vector by a four-by-four unitary matrix. This multiplication redistributes the unit magnitude of the zero-zero state equally between zero-zero and one-zero, placing the vector into a superposition where both states hold equal amplitude. Next, applying a controlled-NOT gate multiplies the resulting vector by another four-by-four matrix. This gate checks the control qubit and swaps the amplitudes of the one-zero state and the one-one state. By swapping these vector elements, the gate transforms the system into an entangled state where the amplitudes for zero-zero and one-one are non-zero, while zero-one and one-zero remain zero.

## 4 - Extracting Answers via Interference and Measurement
> ANIM: Opposite-phase amplitudes cancel out while matching amplitudes constructively interfere, collapsing the vector to state 11 upon simulated measurement.

Maintaining a large state vector is only useful if we can extract a meaningful result. Because probability amplitudes are complex numbers, they possess both a magnitude and a phase. When gate operations combine state paths, amplitudes with matching phases undergo constructive interference, increasing their combined magnitude. Conversely, amplitudes with opposite phases undergo destructive interference, canceling each other out to zero. Quantum algorithms are designed so that wrong computational paths cancel out while correct paths reinforce one another. Finally, observing the system forces the continuous state vector to collapse into a single discrete basis state. The probability of measuring any specific outcome equals the squared magnitude of its amplitude. As interference zeros out unwanted states, the measurement process collapses the vector into state one-one with complete certainty. This raises a crucial question: how do we structure gate sequences so that constructive interference targets the correct answer for arbitrary algorithms?

