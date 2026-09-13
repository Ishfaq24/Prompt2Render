---
title: How Qubits and Quantum Gates Compute
topic: qubits, state vectors, superposition, tensor product state space, unitary matrix gates, quantum interference, measurement collapse
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
> ANIM: A classical 3-bit register holding a single state like 101 is contrasted with a quantum 3-qubit system represented as a vector of 8 complex amplitudes representing all states simultaneously.

How do we represent the vast computational states required to solve problems that classical computers cannot touch? In classical computing, a three-bit register can only store a single configuration at any given moment, such as the binary state one zero one. To represent larger systems, we scale linearly, adding one bit for each extra dimension of state. But a quantum system behaves differently. A three-qubit system does not exist in just one state. Instead, it occupies a superposition of all eight possible states simultaneously. We represent this quantum state as a vector containing eight complex numbers, called amplitudes. Each amplitude corresponds to one of the possible three-bit configurations. As we add more qubits, the size of this state space grows exponentially as two to the power of n. This exponential expansion of the state space allows a quantum computer to manipulate an immense amount of information simultaneously.

## 2 - Representing Qubits as Complex Vectors
> ANIM: A mathematical equation displays a single qubit state vector with amplitudes alpha and beta, mapped to a 2D vector space where the sum of their squared magnitudes equals one.

To understand how this works, we must look at how we represent a single qubit mathematically. We write the state of a single qubit as a two-dimensional vector in a complex vector space. This state is a linear combination of two basic computational states, zero and one. We scale these basis states by two complex coefficients, alpha and beta, which represent probability amplitudes. When we square the absolute value of these amplitudes, we get the actual probability of the qubit collapsing into that state upon measurement. Because the qubit must ultimately resolve to either zero or one, the sum of the squared magnitudes of alpha and beta must equal exactly one. This normalization constraint ensures that the total probability of all possible outcomes always equals one hundred percent.

## 3 - Processing Information with Unitary Gates
> ANIM: A block diagram traces a state vector passing through a Hadamard gate, shown as a 2x2 matrix multiplication that transforms the basis state zero into an equal superposition of zero and one.

We process this quantum information by manipulating the state vector using quantum gates. In classical computing, gates perform boolean operations. In quantum computing, gates are represented as unitary matrices that multiply our state vector to produce a new state vector. Let us trace what happens when we pass the basis state zero through a Hadamard gate. This operation is represented mathematically by multiplying a two-by-two unitary matrix by the vector representing state zero. This multiplication transforms the state zero into an equal superposition of zero and one. Now, the amplitudes for both zero and one are equal, meaning a measurement would yield either result with a fifty percent probability. Because these gates are represented by unitary matrices, they preserve the total probability of the system and ensure that all quantum operations are mathematically reversible.

## 4 - Harnessing Interference for the Final Answer
> ANIM: A bar chart of state amplitudes shows constructive interference raising the probability of the target state 101 while destructive interference zeroes out the others, leading to a measurement block that collapses the system into 101.

Simply putting qubits into superposition is not enough to solve a problem, because a random measurement would yield a random result. To find the correct answer, we must harness quantum interference. Because probability amplitudes are complex numbers, they have both magnitude and phase. This means amplitudes can interfere with each other just like physical waves. We design quantum algorithms so that the amplitudes of incorrect paths interfere destructively, canceling each other out to zero. At the same time, the amplitudes of the correct path interfere constructively, amplifying its probability. For our three-qubit system, we use interference to cancel the amplitudes of the seven incorrect states while maximizing the amplitude of our target state, one zero one. When we finally perform a measurement, the quantum state collapses, and we read out the classical state one zero one with high probability. But how do we physically build hardware that can manipulate these delicate complex amplitudes without introducing errors?

