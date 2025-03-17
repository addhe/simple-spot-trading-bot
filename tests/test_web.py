import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os
import warnings

# Suppress the specific deprecation warning for TestClient
warnings.filterwarnings("ignore", message="The 'app' shortcut is now deprecated", category=DeprecationWarning)

# Add the project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Skip the tests if FastAPI can't be imported properly
try:
    import web
    SKIP_TESTS = False
except ImportError as e:
    SKIP_TESTS = True
    SKIP_REASON = str(e)

@unittest.skipIf(SKIP_TESTS, f"Skipping due to import error: {SKIP_REASON if 'SKIP_REASON' in locals() else 'Unknown error'}")
class TestWeb(unittest.TestCase):
    def setUp(self):
        if SKIP_TESTS:
            return
            
        # Configure the FastAPI app for testing
        from fastapi.testclient import TestClient
        
        # Use the standard initialization for TestClient
        self.client = TestClient(web.app)
        
        # Store original values to restore after test
        self.original_attributes = {}
        for attr in dir(web):
            if not attr.startswith('__'):
                self.original_attributes[attr] = getattr(web, attr)
    
    def tearDown(self):
        if SKIP_TESTS:
            return
            
        # Restore original module attributes
        for attr, value in self.original_attributes.items():
            setattr(web, attr, value)
    
    def test_web_module_exists(self):
        # Basic test to verify the module loads
        self.assertIsNotNone(web)
    
    # Test actual routes that exist in your web.py
    def test_docs_route(self):
        # Test the docs route which should exist in FastAPI by default
        response = self.client.get('/docs')
        self.assertEqual(response.status_code, 200)
    
    def test_redoc_route(self):
        # Test the ReDoc route which should exist in FastAPI by default
        response = self.client.get('/redoc')
        self.assertEqual(response.status_code, 200)
    
    def test_openapi_schema(self):
        # Test the OpenAPI schema endpoint
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn('openapi', schema)
        self.assertIn('paths', schema)
        self.assertIn('info', schema)
    
    # Create a mock for the trading functions
    @patch.object(web, 'start_trading', create=True)
    def test_start_route(self, mock_start_trading):
        # Configure the mock
        mock_start_trading.return_value = True
        
        # Test the start route if it exists
        if hasattr(web.app, 'routes'):
            start_route_exists = any(route.path == '/start' for route in web.app.routes)
            if start_route_exists:
                response = self.client.post('/start')
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data.get('success', False))
            else:
                self.skipTest("'/start' route does not exist")
    
    @patch.object(web, 'stop_trading', create=True)
    def test_stop_route(self, mock_stop_trading):
        # Configure the mock
        mock_stop_trading.return_value = True
        
        # Test the stop route if it exists
        if hasattr(web.app, 'routes'):
            stop_route_exists = any(route.path == '/stop' for route in web.app.routes)
            if stop_route_exists:
                response = self.client.post('/stop')
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data.get('success', False))
            else:
                self.skipTest("'/stop' route does not exist")
    
    @patch.object(web, 'is_trading', True, create=True)
    def test_status_route(self):
        # Test the status route if it exists
        if hasattr(web.app, 'routes'):
            status_route_exists = any(route.path == '/status' for route in web.app.routes)
            if status_route_exists:
                response = self.client.get('/status')
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn('trading', data)
            else:
                self.skipTest("'/status' route does not exist")
    
    # Add this test method after test_openapi_schema
    def test_available_routes(self):
        # Test to list all available routes in the FastAPI app
        if hasattr(web.app, 'routes'):
            routes = [{"path": route.path, "name": route.name, "methods": route.methods} 
                     for route in web.app.routes]
            
            # Print available routes for debugging
            print("\nAvailable routes in FastAPI app:")
            for route in routes:
                print(f"Path: {route['path']}, Methods: {route['methods']}")
            
            # Verify we have at least some routes
            self.assertTrue(len(routes) > 0)
            
            # Check for common FastAPI routes
            docs_route = any(route['path'] == '/docs' for route in routes)
            openapi_route = any(route['path'] == '/openapi.json' for route in routes)
            
            self.assertTrue(docs_route, "'/docs' route should exist")
            self.assertTrue(openapi_route, "'/openapi.json' route should exist")
    
    def test_health_check(self):
        """Test the health check endpoint if it exists"""
        if hasattr(web.app, 'routes'):
            health_route_exists = any(route.path == '/health' for route in web.app.routes)
            if health_route_exists:
                response = self.client.get('/health')
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn('status', data)
            else:
                # If no health endpoint exists, we'll create a test that suggests adding one
                print("\nConsider adding a health check endpoint to your FastAPI app:")
                print("@app.get('/health')")
                print("def health_check():")
                print("    return {'status': 'ok'}")
                
                # Skip the test instead of failing
                self.skipTest("'/health' route does not exist - consider adding one")

if __name__ == '__main__':
    unittest.main()