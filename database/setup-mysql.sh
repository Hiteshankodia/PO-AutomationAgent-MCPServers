#!/bin/bash

echo "Setting up MySQL Database with Podman..."

# Create data directory
mkdir -p database/data

# Copy CSV files to data directory
cp database/*.csv database/data/

# Start MySQL container using Podman
podman-compose -f database/docker-compose.yml up -d

# Wait for MySQL to be ready
echo "Waiting for MySQL to start..."
sleep 30

# Load CSV data
echo "Loading CSV data into MySQL..."

# Load suppliers data
podman exec -i po_automation_mysql mysql -u po_user -ppo_password123 po_automation << EOF
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/data/suppliers.csv' 
INTO TABLE suppliers 
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"' 
LINES TERMINATED BY '\n' 
IGNORE 1 ROWS
(supplier_id, name, status, rating, payment_terms, categories, risk_score, max_order_value, contact_email);
EOF

# Load budgets data
podman exec -i po_automation_mysql mysql -u po_user -ppo_password123 po_automation << EOF
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/data/budgets.csv' 
INTO TABLE budgets 
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"' 
LINES TERMINATED BY '\n' 
IGNORE 1 ROWS
(department_id, name, allocated, spent, reserved, fiscal_year, manager_email);
EOF

# Load approval matrix data
podman exec -i po_automation_mysql mysql -u po_user -ppo_password123 po_automation << EOF
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/data/approval_matrix.csv' 
INTO TABLE approval_matrix 
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"' 
LINES TERMINATED BY '\n' 
IGNORE 1 ROWS
(id, max_amount, required_approvers, auto_approve, description);
EOF

# Load approvers data
podman exec -i po_automation_mysql mysql -u po_user -ppo_password123 po_automation << EOF
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/data/approvers.csv' 
INTO TABLE approvers 
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"' 
LINES TERMINATED BY '\n' 
IGNORE 1 ROWS
(approver_role, name, email, department, active);
EOF

echo "MySQL setup complete!"
echo "Database URL: mysql://po_user:po_password123@localhost:3306/po_automation"
