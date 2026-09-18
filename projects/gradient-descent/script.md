---
title: Understanding Gradient Descent
topic: Optimization and Machine Learning
audience: undergraduate computer science
aspect: 16:9
voice: am_eric
---

## 1 - The Loss Surface and Our Goal
> ANIM: 2D convex bowl loss function with contour curves, showing an initial parameter point high on the ridge with cost value

In machine learning, training a model means finding parameter values that minimize a loss function. Imagine standing on a foggy hillside where elevation represents prediction error. Your objective is simple: reach the deepest point in the valley without being able to see the full landscape.

## 2 - Following the Negative Gradient
> ANIM: loss curve showing tangent line, gradient vector pointing uphill, and opposite step vector pointing downhill toward the minimum

The mathematical key is the gradient vector, written as nabla L. The gradient is a vector of partial derivatives that always points in the direction of steepest ascent. By taking a step in the exact opposite direction, negative nabla L, we guarantee the fastest local decrease in loss.

## 3 - The Role of the Learning Rate
> ANIM: comparison of trajectory steps: small learning rate converging versus large learning rate overshooting the bowl

How far should we step in each iteration? That depends on the learning rate, eta. If eta is too small, convergence takes thousands of steps. If eta is too large, our updates overshoot the valley completely. When tuned properly, gradient descent steps smoothly straight into the minimum.
