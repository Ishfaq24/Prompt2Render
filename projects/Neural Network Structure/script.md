---
title: Anatomy of a Feedforward Neural Network
topic: single perceptron limitations, multi-layer perceptron architecture, affine transformations, activation functions, layer vectorization, forward propagation trace
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

## 1 - Why a Single Neuron Fails on XOR
> ANIM: A 2D scatter plot displays four points representing XOR—(0,0)=0, (0,1)=1, (1,0)=1, (1,1)=0—while a single linear decision boundary spins continuously, unable to separate the classes.

Why does a single artificial neuron fail on a task as simple as the exclusive OR function? A single perceptron computes a linear combination of its inputs and applies a threshold. Geometrically, this means it draws a single straight line through the feature space to separate positive targets from negative targets. For logical functions like AND or OR, a single line easily splits the output zeros from the output ones. But XOR presents a fundamental topological problem. The input points at zero zero and one one evaluate to zero, while the input points at zero one and one zero evaluate to one. No single straight line can ever pass through this two-dimensional plane such that all ones fall on one side and all zeros fall on the other. This non-linear separability is the primary limitation of simple linear classifiers. To solve XOR, a model must construct a more complex decision boundary, which requires moving beyond individual hyperplanes.

## 2 - Stacking Layers to Warp Space
> ANIM: Two separate linear boundary lines slice the 2D plane individually, then merge into a 3D computational graph showing an Input Layer feeding into a 2-neuron Hidden Layer, where non-linear activation bends and folds the coordinate grid to make the XOR points linearly separable.

To break through the limitations of a single decision boundary, we can combine multiple neurons arranged in layers. Running two neurons in parallel allows us to slice the input space twice simultaneously. However, stacking linear operations alone only yields another linear boundary. To truly warp feature space, each neuron must combine its linear sum with a non-linear activation threshold. When we stack these non-linear units into a hidden layer, the original input coordinates are non-linearly transformed into a new intermediate representation. In this folded space, the formerly non-linearly separable XOR points are rearranged so that a final linear output neuron can separate them cleanly. By stacking layers of non-linear computation, we convert complex spatial arrangements into representations that can be untangled linearly.

## 3 - The Mathematical Unit: Weighted Sum and Activation
> ANIM: A single neuron node expands to show incoming signals x_1, x_2 multiplied by weights w_1, w_2, summed with bias b into z, then passed through a ReLU activation function curve.

To understand how each node contributes to this spatial transformation, we look at its underlying mathematical structure. A single artificial neuron performs two distinct operations in sequence: an affine transformation followed by a non-linear activation. First, the node receives input signals x one and x two. It multiplies each input signal by an associated scalar weight, w one and w two, which determines the strength and influence of that input. It sums these weighted signals together and adds a scalar bias, b. The bias shifts the activation threshold, allowing the decision boundary to translate away from the origin. This combined calculation yields an intermediate scalar value, z. Next, z passes through a non-linear activation function, such as the Rectified Linear Unit, or ReLU. The ReLU function sets any negative value of z to zero, while passing positive values through unchanged. This thresholding operation introduces the necessary non-linearity to fold and reshape the feature space.

## 4 - Vectorizing a Single Layer
> ANIM: Multiple scalar equations collapse smoothly into the matrix-vector notation a^(1) = ReLU(W^(1) x + b^(1)), displaying matrix dimensions (3x2) x (2x1) + (3x1) = (3x1).

Writing individual scalar equations for every neuron quickly becomes unwieldy as architectures scale. Instead, we vectorize the entire layer using linear algebra. Consider a hidden layer with three neurons processing a two-dimensional input vector. We group the incoming signals into a column vector x. The weights for all three neurons are organized into a matrix W superscript one, where each row contains the weights belonging to one specific neuron. For three neurons receiving two inputs, this weight matrix has dimensions three by two. Multiplying the three-by-two weight matrix by the two-by-one input vector yields a three-by-one vector of weighted sums. We then add a three-by-one bias vector b superscript one. Finally, we apply the Rectified Linear Unit activation function element-wise to this resulting vector. The entire layer operation collapses into a single matrix equation: a superscript one equals ReLU of W superscript one times x plus b superscript one.

## 5 - Tracing a Payload Through the Network
> ANIM: Animation explicitly displays matrix values: W^(1) = [[2, 0], [1, 1], [0, -1]], b^(1) = [-0.2, 0.5, 0.2]^T, W^(2) = [0.5, 1.0, 0.3], b^(2) = 0.09. Input vector [0.5, -1.2]^T flows into W^(1) x + b^(1) to give [0.8, -0.2, 1.4]^T, which activates via ReLU to hidden vector [0.8, 0.0, 1.4]^T. This vector multiplies by W^(2) and adds b^(2) to yield final output scalar 0.91.

Let us trace a concrete numerical payload as it flows forward through this vectorized network. We begin with a two-dimensional input column vector x containing values zero point five and negative one point two. In the first layer, our three-by-two weight matrix W superscript one has rows two zero, one one, and zero negative one, paired with bias vector b superscript one containing negative zero point two, zero point five, and zero point two. Multiplying W superscript one by x and adding b superscript one gives pre-activation values zero point eight, negative zero point two, and one point four. Passing these through the Rectified Linear Unit sets the negative value to zero, yielding hidden vector a superscript one with values zero point eight, zero point zero, and one point four. Next, layer two applies row weights zero point five, one point zero, and zero point three with a bias of zero point zero nine. Computing zero point five times zero point eight plus zero point three times one point four plus zero point zero nine evaluates to a final output scalar prediction of zero point nine one.

## 6 - The Necessity of Non-Linear Activations
> ANIM: An animation removes the ReLU functions from a 3-layer network, showing the nested matrix multiplications W_3(W_2(W_1 x + b_1) + b_2) + b_3 collapse algebraically into a single linear matrix W_net x + b_net.

It is tempting to assume that deep networks gain their expressive capacity purely from stacking multiple layers of matrix multiplication, but without non-linear activation functions, network depth is mathematically redundant. Suppose we remove the Rectified Linear Unit activation functions from a three-layer network entirely. The forward pass becomes a nested sequence of pure affine transformations: weight matrix W three times the quantity weight matrix W two times the quantity weight matrix W one times x plus bias b one, plus bias b two, plus bias b three. By expanding this expression using basic linear algebra, consecutive matrix multiplications simplify into a single equivalent matrix W net, and the combined bias terms collapse into a single equivalent vector b net. The entire multi-layer architecture reduces back down to a single linear equation: W net times x plus b net. Without non-linear activations between layers, deep neural networks collapse into simple linear models, losing all ability to learn complex decision boundaries.

## 7 - Summary and the Credit Assignment Problem
> ANIM: A full architecture diagram highlights the forward pass arrow from input to output loss, then flashes a red question mark over the internal weight matrices to prompt how weights should update.

We have established how a feedforward neural network uses vectorized linear transformations and non-linear activation functions to map raw inputs into intermediate representations, ultimately yielding an output prediction. During this forward pass, data flows strictly from input to output, where a loss function evaluates the network's prediction against a known target. However, this execution model introduces a fundamental challenge. When the final output contains an error, how do we determine which internal weights within our weight matrices contributed to that error, and by how much should each weight be adjusted? This problem is known as the credit assignment problem. To optimize our network, we must establish a mathematically precise procedure to send error signals backward from the output layer through every matrix multiplication. Solving this requires reversing our computational graph to evaluate partial derivatives with respect to every parameter, leading directly to the backpropagation algorithm.

