---
title: "Backpropagation: The Algorithm That Teaches Neural Networks"
topic: backpropagation, credit assignment problem, chain rule, forward pass, loss gradient, output layer delta, hidden layer delta, weight update rule, vanishing gradients, ReLU, batch normalization, residual connections
audience: undergraduate computer science and AI practitioners
aspect: 16:9
voice: am_eric
renderer: manim
assets: false
---

## 1 - The Credit Assignment Problem

> ANIM: A small 2-layer neural network (2 input, 3 hidden, 1 output) shows a forward pass producing prediction 0.82 while the true label is 0.0; a large red error label "Loss = 0.67" floats over the output, and question marks appear over every weight edge asking which connection is responsible

You have trained a neural network. It made a prediction. The prediction was wrong. Now what? The network has dozens, hundreds, or billions of weights, and you need to decide by exactly how much to nudge each one to reduce the error. Which weights caused the mistake? By how much? This is the credit assignment problem, and it is the core challenge that backpropagation was designed to solve. Without a principled answer, you would be forced to perturb each weight individually and measure whether the loss improves, a strategy that requires one forward pass per parameter and is completely impractical at any real scale. Backpropagation solves this in a single backward pass through the network, computing the exact gradient of the loss with respect to every single weight simultaneously using one foundational tool from calculus: the chain rule.

## 2 - The Chain Rule: Calculus of Responsibility

> ANIM: Three cascaded function boxes: z equals w times a plus b, then a equals sigma of z, then L equals half of y-hat minus y squared; arrows connect them left to right, and then red partial derivative fractions chain backward: dL over dw equals dL over da times da over dz times dz over dw, each factor lighting up in turn

The chain rule tells you how to differentiate a composition of functions. If the loss L depends on activation a, which depends on pre-activation z, which depends on weight w, then the derivative of the loss with respect to that weight is the product of three local derivatives. First, how does the loss change as the activation changes. Second, how does the activation change as the pre-activation changes, which is just the derivative of the activation function. Third, how does the pre-activation change as the weight changes. Each of these local derivatives is simple to compute individually. The chain rule says you multiply them together. This is the entire mathematical foundation of backpropagation. Every complexity you will see afterward is just this same rule applied layer by layer through a network of arbitrary depth.

## 3 - Forward Pass Bookkeeping

> ANIM: A 2-layer network with concrete weights: input x equals [0.5, 0.8], hidden layer weights W1 shown as a 3x2 matrix, output weight W2 shown as a 1x3 vector; a forward pass animates left to right, computing z1 equals W1 times x, then a1 equals sigmoid of z1 at each node, then z2 equals W2 times a1, then y-hat equals sigmoid of z2, with the numerical values appearing at each step and being cached in memory boxes

Before any gradient can be computed, the forward pass must run in full, and every intermediate value must be saved. Given input x, the network computes the pre-activation z at the first hidden layer as the matrix product of the weight matrix W1 and x. Applying the sigmoid activation function element-wise gives the hidden activation vector a1. The pre-activation at the output layer z2 is then the dot product of the output weight vector W2 and a1. Passing z2 through sigmoid gives the final prediction y-hat. These intermediate values, z1, a1, z2, and y-hat, are not discarded after the forward pass. They are cached in memory because the backward pass will need them to compute the local derivatives at each layer. This caching is the key structural reason backpropagation is computationally efficient.

## 4 - Computing the Output Error

> ANIM: A graph shows the MSE loss curve L equals half of (y-hat minus y) squared; a point is marked at y-hat equals 0.82, y equals 0.0, with a vertical red bar showing the residual; the derivative dL over d(y-hat) equals y-hat minus y is annotated as an arrow pointing left, showing the signed gradient of the loss

With the forward pass cached, we are ready to begin the backward pass. The first step is computing the gradient of the loss with respect to the network's output. Using mean squared error, the loss is one-half times the squared difference between prediction and target. The factor of one-half is a mathematical convenience: it cancels the exponent of two when you differentiate, leaving a clean gradient of y-hat minus y. For our example, with y-hat equal to 0.82 and y equal to 0.0, this gradient is positive 0.82. The positive sign tells us the loss increases as the prediction increases, so we must push the prediction downward. This output error signal is the seed from which the entire backward pass grows. Every weight update in the network traces back to this single scalar, propagated backward through the chain rule.

## 5 - Backpropagation Through the Output Layer

> ANIM: The output neuron is highlighted; delta_output is computed as (y-hat minus y) times sigma-prime of z2, shown numerically; then gradient arrows flow backward along each W2 edge, with each gradient labeled as delta_output times a1_j; the weight update rule W2 new equals W2 old minus eta times the gradient appears and the edges visually shift

Now we propagate the error backward through the output layer. We define a local error signal called delta, the Greek letter, for the output layer as the product of the loss gradient and the derivative of the activation function evaluated at the cached pre-activation z2. The derivative of sigmoid is sigma of z times one minus sigma of z, which we can compute directly from the cached activation y-hat. This delta value, call it delta-output, represents how much the total loss responds to a change in the output neuron's pre-activation. The gradient of the loss with respect to each output weight W2 at index j is then simply delta-output multiplied by the corresponding hidden activation a1 at index j. This is the weight gradient for the output layer. We update each weight by subtracting the learning rate times this gradient. The output layer weights are now updated.

## 6 - Backpropagation Through the Hidden Layers

> ANIM: The gradient error flows backward from the output delta through the W2 edges into the hidden layer neurons; for each hidden neuron j, delta_hidden_j equals the sum of W2_j times delta_output times sigma-prime of z1_j, shown with the Hadamard product notation; gradient arrows from each hidden node reach back to the input connections, labeled as delta_hidden times x

The real power of backpropagation reveals itself when we propagate the error signal backward through the hidden layers. Each hidden neuron must receive a share of the output error proportional to how much it contributed. The delta for each hidden neuron j is the output delta weighted by the corresponding output weight W2 at index j, multiplied element-wise by the derivative of the activation function evaluated at the cached hidden pre-activation z1 at index j. More generally, for any hidden layer in a deep network, the delta vector equals the transpose of the next layer's weight matrix multiplied by the next layer's delta, then multiplied element-wise by the activation derivative at the current layer. This is the vectorized backward recurrence that propagates the error signal from output all the way to the first layer. The gradient for each hidden weight W1 at indices i and j is then the hidden delta at index i multiplied by the corresponding input at index j.

## 7 - The Full Weight Update Loop

> ANIM: A complete training loop diagram showing one epoch: sample mini-batch, forward pass fills the cache, backward pass computes all deltas, gradient descent updates W1 and W2; then the loop arrow cycles back; a loss curve plot alongside shows the loss decreasing from 0.67 toward 0.02 over 200 iterations

With all gradients computed, the weight update step is identical for every layer: the new weight equals the old weight minus the learning rate times the gradient. This procedure is run repeatedly. In each training iteration, a mini-batch of examples is sampled, a forward pass runs and caches all intermediate activations, a backward pass computes all the deltas and gradients, and then gradient descent nudges every weight in the direction that reduces the loss. Over thousands of iterations, this feedback loop sculpts the weights of the network from random initialization into a precise configuration that maps inputs to correct outputs. The loss curve drops from its initial high value, oscillating slightly due to mini-batch noise, and converges toward a minimum. Backpropagation is simply the efficient machinery that computes all the weight gradients in one backward sweep.

## 8 - Why Vanishing Gradients Kill Deep Networks

> ANIM: An 8-layer network with sigmoid activations; a bar chart alongside shows the gradient magnitude at each layer from output to input: layer 8 has magnitude 0.20, each bar decreases multiplicatively, and by layer 1 the bar is nearly invisible at 0.0003; the sigmoid derivative curve is shown, peaking at 0.25 near zero and annotated "maximum 0.25"

Backpropagation has a critical failure mode in deep networks: the vanishing gradient problem. The recurrence for computing hidden deltas multiplies through the sigmoid derivative at every layer. The sigmoid function saturates at 0 and 1, and its derivative reaches a maximum of only 0.25 at its center. In a network with eight sigmoid layers, the gradient at the first layer is at most 0.25 raised to the power of eight, which is roughly 0.00015. In practice, because activations are not always at the optimal center, gradients shrink far faster. By the time the error signal reaches the earliest layers, it is so small that the corresponding weight updates are negligible. The first layers stop learning entirely. This is why deep networks with sigmoid activations trained with naive backpropagation performed no better than shallow networks before 2012, and why this problem was the central bottleneck in deep learning for over a decade.

## 9 - Modern Fixes: ReLU, Batch Normalization, and Residual Connections

> ANIM: Left panel shows sigmoid and its derivative side by side; right panel shows ReLU and its derivative, which is a step function equal to 1 for positive inputs; below, a residual block diagram shows input x flowing directly past a two-layer block and being added at the output: F(x) plus x; gradient flow arrows in the residual path are shown as full strength, bypassing the multiplication chain

Three innovations broke through the vanishing gradient wall. First, the Rectified Linear Unit, or ReLU, activation function returns the input directly for positive values and zero for negative values. Its derivative is exactly one for all positive pre-activations. Multiplying a chain of ones does not shrink the gradient. Networks with ReLU activations can train effectively at dozens or hundreds of layers deep. Second, batch normalization normalizes the pre-activations across a mini-batch before applying the activation function, keeping the inputs to each activation centered near zero where gradients are largest, and dramatically stabilizing training. Third, residual skip connections, introduced in ResNet, add a direct path from a layer's input to its output that bypasses the weight computation. During backpropagation, the gradient of the loss flows through this skip connection without passing through any multiplicative derivatives, giving early layers a high-strength gradient signal regardless of network depth. Together, these three innovations made training networks with hundreds of layers not just possible but routine.

## 10 - Putting It All Together

> ANIM: An infographic-style summary showing the full training loop in five labeled panels flowing in a cycle: (1) Forward Pass — cache z and a at every layer, (2) Compute Loss — L equals MSE of y-hat versus y, (3) Output Delta — delta equals gradient of L times sigma-prime of z, (4) Backward Recurrence — delta_prev equals W^T times delta times sigma-prime of z_prev, (5) Weight Update — W new equals W old minus eta times delta times a^T; arrows cycle back to panel 1

Backpropagation is the closed-loop learning algorithm at the heart of every modern neural network. In a single training step, the forward pass maps the input through every layer, computing and caching the pre-activations and activations that the backward pass will need. The loss function measures the discrepancy between the prediction and the target. The backward pass starts at the output, seeds the chain rule with the loss gradient, and propagates error signals backward through every layer via the recurrence relation on the delta vectors. The weight gradients emerge naturally from this process, and gradient descent applies them to reduce the loss. This cycle repeats over millions of iterations and billions of parameters. With ReLU activations preventing gradient starvation, batch normalization stabilizing the distribution of pre-activations, and residual connections delivering full-strength gradients to early layers, backpropagation scales from the toy two-layer network we analyzed today to the hundred-billion-parameter transformers that define the current frontier of artificial intelligence.
