---
title: Anatomy of a Feedforward Neural Network
topic: feedforward neural networks - perceptrons, linear non-separability, weight matrices, bias vectors, activation functions, stacked layers, matrix-vector forward pass
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

## 1 - The Limits of Linear Decision Boundaries
> ANIM: A 2D scatter plot showing four data points representing an XOR pattern, with a straight line attempting and failing to separate the two classes.

How can a computer classify data when a single straight line cannot separate the classes? Consider the exclusive or operation, where two inputs produce a positive output only when exactly one of them is active. If you place these four binary combinations on a two dimensional grid, no single linear decision boundary can ever divide the true outputs from the false outputs. A standard linear model, such as a logistic regression classifier or a single perceptron, calculates a single linear boundary across its input space. Because that boundary is strictly flat, it will always misclassify at least one point in an exclusive or pattern. To solve problems where data is non-linearly separable, we must construct models capable of bending, warping, and dividing space in complex ways. That requirement brings us to the structure of artificial neural networks.

## 2 - Inside an Artificial Neuron
> ANIM: A diagram of a single neuron receiving input vector [2.0, -1.0], computing a dot product with weight vector [0.5, 1.5], adding bias 0.2, and outputting pre-activation scalar -0.3.

To build a system capable of solving non-linear problems, we start with its most fundamental component, the artificial neuron. A single neuron takes a vector of numerical inputs, scales each input by a corresponding weight parameter, adds all the products together, and adds a scalar term called the bias. Suppose our input vector contains the values two point zero and negative one point zero. The neuron assigns a weight vector of zero point five and one point five. Multiplying two point zero by zero point five gives one point zero, and multiplying negative one point zero by one point five gives negative one point five. Summing those yields negative zero point five. We then add a bias vector term of zero point two, resulting in a single pre-activation scalar value of negative zero point three. This combination of a dot product and a bias sum is a purely linear transformation.

## 3 - Breaking Linearity with Activation Functions
> ANIM: A side-by-side plot comparing pre-activation input z to post-activation outputs for ReLU, Sigmoid, and GELU, showing how negative values are zeroed or smoothed.

If every neuron performs only linear arithmetic, then stacking a thousand neurons together would still result in a simple linear function. To introduce non-linearity into the network, we pass the pre-activation scalar through an activation function. Consider our pre-activation value of negative zero point three. If we pass this through the rectified linear unit activation function, any negative input is immediately capped at zero, so negative zero point three becomes zero point zero, while positive values pass through unchanged. Alternatively, the sigmoid activation function squashes any input value into a smooth curve bounded between zero and one, turning negative zero point three into approximately zero point forty-two. A smoother alternative like the gaussian error linear unit gently scales negative inputs while remaining nearly linear for positive inputs. By applying these non-linear functions after every linear operation, the network gains the ability to learn highly complex decision boundaries.

## 4 - From Single Neurons to Layer Matrices
> ANIM: An animated matrix multiplication where a 2D input vector is multiplied by a 3x2 weight matrix W and added to a 3D bias vector b to form a 3D hidden layer vector.

Rather than calculating each neuron individually, we group parallel neurons into a structural layer using matrix linear algebra. Suppose we want to transform a two dimensional input vector into a three dimensional hidden layer. Instead of running three separate dot products, we assemble the weight vectors of all three neurons into a single weight matrix with three rows and two columns. When we multiply this three-by-two weight matrix by our two dimensional input vector, matrix multiplication simultaneously computes the weighted sums for all three neurons at once. We then add a three dimensional bias vector, where each element corresponds to the individual bias of one neuron. The result is a single three dimensional pre-activation vector. Expressing an entire layer as a single matrix multiplication plus a bias vector allows computer hardware to process millions of neuronal operations in parallel.

## 5 - Stacking Layers to Transform Feature Space
> ANIM: A full network diagram showing a 2-node input layer, a 3-node hidden layer, and a 1-node output layer, visualizing how the hidden layer warps the non-linear XOR space into a 3D linearly separable space.

When we chain these matrix transformations together across successive layers, the network radically alters how data is represented. Consider a feedforward network designed for the exclusive or problem, equipped with a two node input layer, a three node hidden layer, and a one node output layer. The input space begins as a flat two dimensional grid where the points cannot be separated by a line. As the two dimensional input passes into the three-by-two weight matrix and through the non-linear activation function, it is projected into a three dimensional hidden feature space. In this expanded three dimensional coordinate system, the activation function folds and warps the space, repositioning the data points. Points that were originally tangled together on a flat plane are now separated along a third axis, allowing a single linear plane at the output layer to divide them perfectly.

## 6 - Tracing a Full Forward Pass
> ANIM: Data flow trace pushing input vector [1.0, 0.0] through specific weight matrices and ReLU activations step-by-step to compute intermediate vector [0.8, 0.0, 1.2] and final scalar output 0.95.

Let us trace a complete forward pass through this network using concrete numbers. We feed in an input vector containing one point zero and zero point zero. First, this two dimensional input vector is multiplied by our three-by-two hidden weight matrix, and we add the three dimensional hidden bias vector. The resulting pre-activation vector is passed elementwise through the rectified linear unit activation function, zeroing out any negative components and yielding an intermediate hidden vector of zero point eight, zero point zero, and one point two. Next, to compute the final output, this three dimensional hidden vector is multiplied by the output weight matrix, which has one row and three columns, and we add the scalar output bias. The resulting value is passed through the final activation function, arriving at a final output scalar of zero point ninety-five.

## 7 - Summary and the Parameter Problem
> ANIM: A high-level network schematic summarizing matrix dimensions across layers, highlighting all weight and bias matrices with question marks to ask how these parameters are learned from data.

A feedforward neural network is ultimately a sequence of matrix multiplications, vector additions, and non-linear activations. An input vector passes from layer to layer, shifting dimensions according to the shape of each weight matrix, until it produces a final prediction vector. However, this full pipeline relies on having exact numerical values for every weight matrix and bias vector across all layers. If those values are chosen at random, the forward pass will produce entirely wrong output predictions. How does a network automatically determine the correct numbers for every weight matrix and bias vector across all these layers to accurately model real world data? That question brings us to loss functions, gradients, and the backpropagation algorithm.

