import pytest
from unittest.mock import MagicMock, patch
from app import app
import json

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch('app.supabase')
def test_api_activate_success(mock_supabase, client):
    # Mock data
    mock_supabase.table().select().eq().execute.return_value.data = [{
        'license_key': 'CURE-TEST-KEY',
        'is_activated': True,
        'expires_at': '2030-01-01',
        'max_terminals': 2,
        'machine_ids': '[]',
        'pharmacy_name': None,
        'max_users': 5,
        'activated_at': None,
        'plan': 'Standard'
    }]
    
    response = client.post('/api/activate', json={
        'license_key': 'CURE-TEST-KEY',
        'machine_id': 'MAC1',
        'pharmacy_name': 'Test Pharma',
        'contact': 'John',
        'phone': '123'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert data['valid'] is True
    assert data['pharmacy_name'] == 'Test Pharma'

@patch('app.supabase')
def test_api_validate_expired(mock_supabase, client):
    mock_supabase.table().select().eq().execute.return_value.data = [{
        'license_key': 'CURE-TEST-KEY',
        'is_activated': True,
        'expires_at': '2020-01-01', # Expired
        'machine_ids': '["MAC1"]',
        'plan': 'Standard',
        'max_users': 5
    }]
    
    response = client.post('/api/validate', json={
        'license_key': 'CURE-TEST-KEY',
        'machine_id': 'MAC1'
    })
    
    assert response.status_code == 402
    data = response.get_json()
    assert data['valid'] is False
    assert data['error'] == "Expired"

@patch('app.supabase')
def test_api_transfer_success(mock_supabase, client):
    mock_supabase.table().select().eq().execute.return_value.data = [{
        'license_key': 'CURE-TEST-KEY',
        'is_activated': True,
        'machine_ids': '["MAC_OLD"]',
    }]
    
    response = client.post('/api/transfer', json={
        'license_key': 'CURE-TEST-KEY',
        'old_machine_id': 'MAC_OLD',
        'new_machine_id': 'MAC_NEW',
        'reason': 'New PC'
    })
    
    assert response.status_code == 200
    assert response.get_json()['success'] is True
