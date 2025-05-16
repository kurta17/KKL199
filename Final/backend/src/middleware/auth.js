const jwt = require('jsonwebtoken');

/**
 * Authentication middleware to verify JWT tokens
 */
function auth(req, res, next) {
  try {
    // Get token from header
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ success: false, message: 'No token provided' });
    }
    
    const token = authHeader.split(' ')[1];
    
    // Verify token
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    
    // Add user data to request
    req.user = decoded;
    
    next();
  } catch (error) {
    console.error('Auth middleware error:', error);
    return res.status(401).json({ success: false, message: 'Invalid token' });
  }
}

module.exports = auth;
