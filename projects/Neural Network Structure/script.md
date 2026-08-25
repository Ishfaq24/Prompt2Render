---
title: Inside the Feedforward Neural Network
topic: feedforward neural networks, multi-layer perceptrons, node weights and biases, activation functions, matrix representation, forward propagation
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~11 min total = ~1540 words
     across 7 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - The Limits of Linear Classifiers
> ANIM: A 2D scatter plot of the XOR problem with points at (0,0), (1,1) in red and (0,1), (1,0) in blue, showing a single straight decision boundary line rotating and failing to separate the classes.

How do we teach a computer to solve problems where a simple straight line is never enough? Consider the classic exclusive-or problem, where two red points sit at opposite corners and two blue points occupy the remaining corners. Try to draw a single straight decision boundary through this coordinate space, and you will find it fundamentally impossible. No matter how you rotate or shift that line, it will always lump at least one red point on the wrong side of the divide with the blue points. Linear classifiers fail completely here because the underlying data distribution is inherently non-linear. To solve this, we need a way to transform the input space itself rather than relying on a flat dividing line.

## 2 - Bending Space with Hidden Layers
> ANIM: An animated diagram showing the 2D XOR input space morphing and stretching into a 3D space where a single flat plane can now cleanly separate the red and blue coordinates.

We solve the limitation of linear models by introducing hidden layers that actively warp and bend the input space. When we feed our tangled two-dimensional coordinates through these intermediate transformations, the geometry itself stretches and folds. This reshaping lifts the points into a higher dimensional space where the classes finally pull apart from one another. Once the space is properly curved, a single flat plane can slice right between the red and blue coordinates with complete separation. The hidden layers act as feature extractors, reshaping raw inputs into a representation where classification becomes a simple linear task.

## 3 - The Anatomy of a Single Neuron
> ANIM: A detailed node diagram tracing inputs x1=0.5 and x2=-0.8 multiplying along weighted edges w1=1.2 and w2=-0.4, summing together with a bias b=+0.1 to produce an intermediate value z.

To understand how this transformation happens, we have to look inside the fundamental building block of the network, which is the individual artificial neuron. Imagine we have two specific inputs, where x1 is zero point five and x2 is negative zero point eight. Each incoming connection carries a weight that determines its importance. Here, the weight w1 is one point two, and the weight w2 is negative zero point four. Each input multiplies by its corresponding weight, and these products flow into the node together. A bias term, in this case b equals positive zero point one, is added directly to that sum. This combination produces a raw intermediate value known as z.

## 4 - Breaking Linearity with Activations
> ANIM: A split-screen graph showing how the raw sum z passes through a ReLU and Sigmoid curve to produce a squeezed, non-linear output activation value a.

That raw intermediate sum z is still just a linear combination, which means stacking layers without something extra would collapse right back into a single linear function. To prevent this, the value passes through a non-linear activation function. If we route our sum through a Rectified Linear Unit, or ReLU, negative values drop to zero while positive values pass straight through. Alternatively, passing the sum through a Sigmoid curve squeezes that output into a smooth range between zero and one. In both cases, this operation transforms the raw sum into a final activation value a, injecting the non-linear capability required to bend our decision boundaries.

## 5 - Scaling to Matrices
> ANIM: A transformation of individual node connection lines into a structured matrix-vector multiplication equation, highlighting the dimensions of the weight matrix W, bias vector b, and activation vector a.

When we scale these individual calculations across an entire network, we move from scalar equations to structured matrix-vector operations. Instead of tracking every single node connection by hand, we group the weights into a cohesive matrix W and combine the biases into a vector b. The incoming layer values form an input vector that multiplies directly with the weight matrix before the bias vector is added. This matrix representation allows modern processors to compute the operations for thousands of neurons simultaneously. The resulting output vector a holds the activations for the entire layer, ready to be passed forward as the input for the next stage.

## 6 - Tracing the Forward Pass
> ANIM: An animated schematic of a three-layer network where a concrete 2-element input vector flows left-to-right, lighting up nodes and updating vector values at each layer until a final prediction is output.

Now we can trace this entire process as a forward pass through a complete three-layer network. We start with our concrete two-element input vector, where x1 is zero point five and x2 is negative zero point eight. These values flow from left to right across the weighted connections, updating the intermediate sums and activation values at every hidden node in sequence. The resulting vectors transform step by step as they move deeper into the architecture. By the time the signals reach the output layer, they have resolved into a final prediction vector that represents the network decision for that specific input.

## 7 - The Learning Problem
> ANIM: A high-level view of the complete network structure with a sliding loss-function gauge on the right, pointing to the question of how to automatically tune the millions of weights to minimize error.

We have built a system that can compute complex non-linear functions through weighted connections and activation transformations, but this leaves us with a massive optimization challenge. A practical network contains thousands or even millions of these weights and biases, and we cannot set them by hand. On the right side of our architecture, a loss function gauge measures the exact error of our current predictions against the true targets. This brings us to the central question of how we can automatically tune all of those interconnected parameters to drive the error down to zero.

