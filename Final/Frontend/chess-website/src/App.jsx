import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Welcome from './Welcome';
import Login from './Login';
import Register from './Register';
import Game from './Game';
import BlockchainExplorer from './BlockchainExplorer';
import Navbar from './Navbar'; // Import the Navbar
import './App.css'; // Assuming you might have some global styles not in index.css

// Simple HOC for protected routes
const ProtectedRoute = ({ children }) => {
  const isAuthenticated = !!localStorage.getItem('userToken'); // Check for mock token

  if (!isAuthenticated) {
    // User not authenticated, redirect to login page
    // Using an alert for demo as per original, but a toast notification would be better UX
    alert("Please log in to access the game. (This is a simulated auth check)");
    return <Navigate to="/login" replace />;
  }

  return children;
};

function App() {
  return (
    <>
      <Navbar /> {/* Navbar is present on all pages */}
      {/* pt-5 ensures content isn't hidden by fixed navbar */}
      <main className="pt-5 mt-4"> {/* Add padding to avoid content being hidden under navbar */}
        <Routes>
          <Route path="/" element={<Welcome />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/explorer" element={<BlockchainExplorer />} />
          <Route
            path="/game"
            element={
              <ProtectedRoute>
                <Game />
              </ProtectedRoute>
            }
          />
          {/* Fallback route: redirects any unmatched URL to the homepage */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}

export default App;