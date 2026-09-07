---
title: The Geometric Fourier Transform
topic: Fourier transform, signals, sine waves, complex plane, frequency spectrum
audience: undergraduate engineering
---

## 1 - The Puzzle of Composite Frequencies
> ANIM: [manim] Show two pure sine waves of frequency 2Hz and 5Hz in cyan and amber on a 2D coordinate plot. Animate their addition into a single combined composite wave.

Imagine hearing a chord played on a piano. Your ear receives a single complex pressure wave vibrating through the air, yet your brain effortlessly distinguishes each individual musical note. How is this decomposition possible mathematically? The answer is the Fourier Transform. Any continuous periodic signal, no matter how jagged or intricate, can be broken down into a sum of simple, pure sine and cosine waves, each with its own specific frequency, amplitude, and phase.

## 2 - Wrapping Signals Around the Complex Circle
> ANIM: [manim] Show a 2D complex plane with real and imaginary axes. Take the composite waveform and dynamically wrap it around the unit circle as a winding frequency knob rotates from 0Hz to 3Hz.

The core insight of the Fourier transform is taking this time signal and wrapping it around a circle in the complex plane using Euler's formula, e to the minus two pi i times frequency times t. As we vary the winding frequency, the shape of the wrapped graph constantly morphs. When the winding frequency is mismatched, the signal spreads out uniformly around the origin. But when the winding frequency exactly matches a natural frequency of our signal, the points constructively bunch up on one side, shifting the center of mass away from zero.

## 3 - The Frequency Spectrum Peak
> ANIM: [manim] Draw a frequency domain plot below the complex circle. As the winding frequency hits 2Hz and 5Hz, drop glowing projection lines down to mark sharp spikes on the frequency spectrum axis.

By measuring how far this center of mass moves as a function of the winding frequency, we calculate the Fourier integral. Whenever our winding frequency coincides with a constituent frequency in the original sound, the center of mass peaks dramatically. Plotting this center of mass against frequency reveals the frequency spectrum. This beautiful geometric transformation turns a confusing waveform in the time domain into a crystal-clear, interpretable map of pure frequencies.
