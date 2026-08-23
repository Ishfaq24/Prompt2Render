---
title: How Artificial Neural Networks Actually Represent Functions
topic: artificial neural networks - biological inspiration vs mathematical abstraction, perceptrons and decision boundaries, multi-layer feedforward architecture, weight matrices and bias vectors, forward propagation, universal approximation theorem
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; ~13 min total = ~1820 words
     across 8 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build. -->

## 1 - Why do we stack linear equations to recognize images?
> ANIM: Draw a single 2D scatter plot with linearly inseparable points (XOR problem), showing that a single straight line fails to separate them, motivating the need for a multi-layered approach.

Why do we stack linear equations to recognize images? If you plot a simple dataset where the positive and negative examples wrap around each other, a single straight line can never separate the two classes cleanly. One linear function gives you one flat cut through your data space. Real-world patterns like handwritten digits or faces are fundamentally intertwined, meaning any single line leaves massive classification errors on both sides. To solve this, we have to bend, warp, and fold our coordinate space, which requires combining multiple linear decisions into a richer, compound structure.

## 2 - The Single Neuron as a Weighted Sum and Threshold
> ANIM: Build a single node taking inputs x1 and x2, multiplying them by weights w1 and w2, adding bias b, and passing the result through a step function to draw a single decision boundary line.

At the absolute foundation of this architecture sits the artificial neuron, a direct mathematical abstraction of its biological counterpart. It takes incoming numerical signals, scales each one by a specific importance value known as a weight, and sums them all together alongside an added bias term that shifts the entire activation threshold. If that total weighted sum crosses a designated zero threshold, the neuron fires an active signal. Geometrically, this single computational unit acts as a linear boundary equation, slicing the input plane into a binary yes-or-no region.

## 3 - From Step Functions to Smooth Non-Linearities
> ANIM: Show a side-by-side graph morphing a sharp step function into a smooth Sigmoid and ReLU activation function, explaining why gradients require differentiability.

A hard binary step function works for basic logic, but it completely breaks down when we try to optimize our parameters automatically. Because its derivative is zero everywhere except at the exact threshold where it is undefined, gradient-based learning algorithms receive no directional feedback on how to adjust their parameters. To fix this, we replace the sharp step with a smooth, continuous non-linear activation function like the sigmoid or the rectified linear unit. This slight curvature ensures that tiny adjustments to our inputs produce smooth, measurable changes in the output, providing the crucial gradient slope that learning requires.

## 4 - Mapping the Multi-Layer Architecture
> ANIM: Draw a complete feedforward network diagram with an input layer (3 nodes), two hidden layers (4 nodes each), and an output layer (2 nodes), labeling weights w and biases b on connections.

When we wire many of these neurons together, we build a multi-layer feedforward network with distinct functional zones. Information enters through an input layer of three nodes, passes sequentially through two hidden layers containing four nodes each, and finally exits through a two-node output layer. Every single connection between adjacent nodes represents a trainable parameter, governed by specific weights and biases. Data flows strictly forward through this directed graph, with each successive layer transforming the representation handed to it by the previous one.

## 5 - Matrix Multiplication as Layer Transformation
> ANIM: Display an input vector multiplied by a weight matrix W^{(1)} plus bias vector b^{(1)}, showing the dimension transformations from input space to hidden feature space.

Mathematically, moving information across a layer is nothing more than a series of linear algebra operations. We take our incoming feature vector, multiply it by a weight matrix, and add a bias vector to shift the coordinate origin. This matrix multiplication actively stretches, rotates, and shears the input space into a new dimensionality. Applying our non-linear activation function right after this matrix operation then bends that newly transformed space, allowing the network to capture complex geometric relationships.

## 6 - Tracing a Single Forward Pass with Concrete Values
> ANIM: Trace a specific input vector [0.5, -1.2] step-by-step through the network diagram, showing numeric values computed at each node up to the final output layer.

Let us trace this exact forward pass using concrete values, following an input vector of zero point five and negative one point two. We multiply these specific numbers by the first layer weight matrix, add our bias vector terms, and compute the resulting pre-activation sums. Passing those values through our non-linear activation function gives us a new coordinate vector of length four. We feed those intermediate results into the second hidden layer, apply the next weight matrix and bias vector, and propagate the transformed values all the way forward until the final output nodes yield our ultimate prediction scores.

## 7 - The Universal Approximation Theorem in Action
> ANIM: Animate multiple piecewise linear decision boundaries combining in a 2D plane to approximate a complex circular region, illustrating how hidden layers warp space.

When you stack these linear transformations and non-linear bends together, the network implements the universal approximation theorem in practice. Each hidden layer adds another set of piecewise linear boundaries that carve up the input space into increasingly intricate polygonal regions. As you add more neurons and layers, these combined boundaries can tightly hug and approximate almost any continuous function of arbitrary complexity. The network is essentially learning a hierarchical coordinate transformation, gradually turning raw pixel intensities into cleanly separable semantic categories.

## 8 - Summary and the Challenge of Learning
> ANIM: Recap the forward pass mapping from inputs to outputs via stacked matrix operations, ending with a highlighted question mark over the weight values and the prompt: how do we automatically find the correct weights?

Every prediction your network makes is just the end result of stacked matrix multiplications and smooth non-linear function activations cascading from inputs to outputs. But all of this machinery relies entirely on having the correct numerical values for every single weight and bias in the system. Right now, those crucial parameters are just arbitrary placeholders sitting in our matrices. How do we automatically find the correct weights that minimize our errors?

