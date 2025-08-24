-- Create database
CREATE DATABASE IF NOT EXISTS po_automation;
USE po_automation;

-- Create suppliers table
CREATE TABLE suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status ENUM('approved', 'pending', 'suspended') DEFAULT 'pending',
    rating DECIMAL(3,2) DEFAULT 0.0,
    payment_terms VARCHAR(20),
    categories JSON,
    risk_score ENUM('low', 'medium', 'high') DEFAULT 'medium',
    max_order_value DECIMAL(15,2) DEFAULT 0.00,
    contact_email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create budgets table
CREATE TABLE budgets (
    department_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    allocated DECIMAL(15,2) DEFAULT 0.00,
    spent DECIMAL(15,2) DEFAULT 0.00,
    reserved DECIMAL(15,2) DEFAULT 0.00,
    fiscal_year YEAR NOT NULL,
    manager_email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create approval_matrix table
CREATE TABLE approval_matrix (
    id INT AUTO_INCREMENT PRIMARY KEY,
    max_amount DECIMAL(15,2) NOT NULL,
    required_approvers JSON,
    auto_approve BOOLEAN DEFAULT FALSE,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create approvers table
CREATE TABLE approvers (
    approver_role VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    department VARCHAR(100),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create budget_reservations table for tracking PO reservations
CREATE TABLE budget_reservations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    po_id VARCHAR(50) NOT NULL,
    department_id VARCHAR(20) NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    status ENUM('active', 'released', 'consumed') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES budgets(department_id)
);

-- Create indexes
CREATE INDEX idx_suppliers_status ON suppliers(status);
CREATE INDEX idx_budgets_fiscal_year ON budgets(fiscal_year);
CREATE INDEX idx_approval_matrix_amount ON approval_matrix(max_amount);
CREATE INDEX idx_budget_reservations_po ON budget_reservations(po_id);
