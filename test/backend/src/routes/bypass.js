/**
 * Bypass Routes
 * 
 * These routes provide special endpoints that bypass normal authentication
 * restrictions for development purposes. These should NOT be used in production.
 */

const express = require('express');
// Try to load the simple-bypass controller first, fall back to bypass-auth
let authController;
try {
  authController = require('../controllers/simple-bypass');
  console.log('Using simple-bypass controller');
} catch (error) {
  try {
    authController = require('../controllers/bypass-auth');
    console.log('Using bypass-auth controller');
  } catch (error) {
    console.error('No bypass controller available:', error.message);
    authController = {
      register: (req, res) => res.status(500).json({ 
        success: false, 
        message: 'Bypass controller not available' 
      }),
      login: (req, res) => res.status(500).json({ 
        success: false, 
        message: 'Bypass controller not available' 
      })
    };
  }
}

const router = express.Router();

// Authentication routes
router.post('/register', authController.register);
router.post('/login', authController.login);

// Export the router
module.exports = router;
