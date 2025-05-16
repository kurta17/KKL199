// filepath: /Users/levandalbashvili/Documents/GitHub/chessweb/backend/src/routes/dev.js
/**
 * Development-only routes for testing
 */

const express = require('express');
const router = express.Router();
const { supabase, supabaseAdmin } = require('../utils/supabase');

// Simple test endpoint
router.get('/test', (req, res) => {
  res.json({ 
    message: 'Dev routes working',
    timestamp: new Date().toISOString()
  });
});

// List all users in the system - DEV ONLY
router.get('/users', async (req, res) => {
  try {
    // Get users from our custom users table
    const { data: users, error } = await supabase
      .from('users')
      .select('*');
      
    if (error) {
      console.error('Error fetching users:', error);
      return res.status(500).json({
        success: false,
        message: 'Error fetching users'
      });
    }
    
    res.status(200).json({
      success: true,
      users
    });
  } catch (error) {
    console.error('Error in /users endpoint:', error);
    res.status(500).json({
      success: false,
      message: 'Server error'
    });
  }
});

// DEV ONLY: Force sign in a user without email verification
router.post('/force-login', async (req, res) => {
  try {
    const { email, password, autoConfirm = false } = req.body;
    
    if (!email || !password) {
      return res.status(400).json({
        success: false,
        message: 'Email and password are required'
      });
    }

    // For development environment only: allow bypassing normal authentication
    if (autoConfirm) {
      console.log('Using development bypass authentication for:', email);
      
      // Get the user from our users table directly
      const { data: userData, error: userError } = await supabase
        .from('users')
        .select('*')
        .eq('email', email)
        .single();
        
      if (userError) {
        console.error('Error finding user:', userError);
        return res.status(404).json({
          success: false,
          message: 'User not found'
        });
      }
      
      // Generate a development JWT token
      const devToken = require('jsonwebtoken').sign(
        { 
          id: userData.id, 
          email: userData.email,
          username: userData.username,
          publicKey: userData.public_key
        },
        process.env.JWT_SECRET,
        { expiresIn: '7d' }
      );
      
      // Return user data with our custom token
      return res.status(200).json({
        success: true,
        message: 'Development bypass: Login successful',
        token: devToken,
        user: {
          id: userData.id,
          username: userData.username,
          email: userData.email,
          publicKey: userData.public_key,
          rating: userData.rating
        },
        dev: true
      });
    }
    
    // Normal authentication flow
    const { data: authData, error: authError } = await supabaseAdmin.auth.signInWithPassword({
      email,
      password
    });
    
    if (authError) {
      console.error('Force login error:', authError);
      return res.status(401).json({
        success: false,
        message: 'Invalid credentials for force login'
      });
    }
    
    // Get user data from our custom users table
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('*')
      .eq('id', authData.user.id)
      .single();
      
    if (userError) {
      console.error('Error fetching user data:', userError);
      return res.status(500).json({
        success: false, 
        message: 'Error fetching user data'
      });
    }
    
    // Return user data and access token
    res.status(200).json({
      success: true,
      message: 'Force login successful',
      token: authData.session.access_token,
      user: {
        id: userData.id,
        username: userData.username,
        email: userData.email,
        publicKey: userData.public_key,
        rating: userData.rating
      }
    });
  } catch (error) {
    console.error('Error in force-login:', error);
    res.status(500).json({
      success: false,
      message: 'Server error'
    });
  }
});

module.exports = router;
