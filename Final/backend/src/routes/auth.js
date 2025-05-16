const express = require('express');
const router = express.Router();
const authController = require('../controllers/auth');

// Register new user
router.post('/register', authController.register);

// Login user
router.post('/login', authController.login);

// Verify email
router.get('/verify/:token', authController.verifyEmail);

// Request password reset
router.post('/forgot-password', authController.forgotPassword);

// Reset password
router.post('/reset-password/:token', authController.resetPassword);

module.exports = router;
