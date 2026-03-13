#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# OpenClaw Recovery Script
# =============================================================================
# Location: ~/openclaw-dev/scripts/openclaw-recover.sh
# Purpose: Disaster recovery and health maintenance for OpenClaw
# Based on: ~/openclaw-dev/projects/openclaw-disaster-recovery.md
# =============================================================================

set -o pipefail

# -----------------------------------------------------------------------------
# Configuration & Paths
# -----------------------------------------------------------------------------
OPENCLAW_DIR="${HOME}/.openclaw"
DEV_DIR="${HOME}/openclaw-dev"
CONFIG_FILE="${OPENCLAW_DIR}/openclaw.json"
WORKSPACE_DIR="${OPENCLAW_DIR}/workspace"
EXTENSIONS_DIR="${OPENCLAW_DIR}/extensions"
LOGS_DIR="${OPENCLAW_DIR}/logs"
RECOVERY_LOG="${LOGS_DIR}/recovery.log"

# Backup file locations
BACKUP_FILES=(
    "${OPENCLAW_DIR}/openclaw.json.bak.1"
    "${OPENCLAW_DIR}/openclaw.json.bak.2"
    "${OPENCLAW_DIR}/openclaw.json.damaged"
)

# Colors for output
COLOR_RESET='\033[0m'
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[0;33m'
COLOR_CYAN='\033[0;36m'
COLOR_BOLD='\033[1m'

# Flags
FORCE_YES=false
VERBOSE=false

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

# Log message to file and optionally to stdout
log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Ensure log directory exists
    mkdir -p "${LOGS_DIR}"
    
    # Append to log file
    echo "[${timestamp}] [${level}] ${message}" >> "${RECOVERY_LOG}"
    
    # Output to stdout if not quiet mode
    if [[ "$VERBOSE" == "true" || "$level" == "ERROR" || "$level" == "WARN" || "$level" == "INFO" ]]; then
        echo -e "[${timestamp}] [${level}] ${message}"
    fi
}

# Print colored output
print_success() {
    echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"
}

print_error() {
    echo -e "${COLOR_RED}✗${COLOR_RESET} $1"
}

print_warning() {
    echo -e "${COLOR_YELLOW}⚠${COLOR_RESET} $1"
}

print_info() {
    echo -e "${COLOR_CYAN}ℹ${COLOR_RESET} $1"
}

print_header() {
    echo -e "${COLOR_BOLD}$1${COLOR_RESET}"
}

# Confirm action with user (unless --yes flag is set)
confirm_action() {
    local prompt="$1"
    if [[ "$FORCE_YES" == "true" ]]; then
        return 0
    fi
    
    while true; do
        read -p "$prompt [y/N] " yn
        case $yn in
            [Yy]*) return 0 ;;
            [Nn]*|"") return 1 ;;
            *) echo "Please answer yes or no." ;;
        esac
    done
}

# Check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Check if file contains valid JSON
is_valid_json() {
    local file="$1"
    if [[ -f "$file" ]]; then
        python3 -m json.tool "$file" > /dev/null 2>&1
        return $?
    fi
    return 1
}

# -----------------------------------------------------------------------------
# Diagnostic Functions
# -----------------------------------------------------------------------------

# Check Gateway status
check_gateway() {
    print_header "=== Gateway Status ==="
    
    # First check if openclaw command itself works
    local openclaw_test
    openclaw_test=$(openclaw --version 2>&1) || true
    
    # Detect broken openclaw command - check for the specific error pattern
    # This happens when shebang #!/usr/bin/env node fails (env not found)
    if echo "$openclaw_test" | grep -qE "bad interpreter.*No such file|No such file.*env"; then
        print_error "OpenClaw COMMAND IS BROKEN (shebang issue)"
        print_info "Error: /usr/bin/env not found - Termux path issue"
        print_info "Workaround: Use 'node /path/to/openclaw.mjs' directly"
        log "ERROR" "OpenClaw command broken: /usr/bin/env not found"
        return 1
    fi
    
    if echo "$openclaw_test" | grep -qi "bad interpreter\|cannot execute"; then
        print_error "OpenClaw COMMAND IS BROKEN"
        print_info "Error: $openclaw_test"
        log "ERROR" "OpenClaw command is broken: $openclaw_test"
        return 1
    fi
    
    local gateway_status
    gateway_status=$(openclaw gateway status 2>&1 || echo "UNKNOWN")
    
    if echo "$gateway_status" | grep -qiE "running|started|active|RPC probe.*ok|bind="; then
        print_success "Gateway is RUNNING"
        log "INFO" "Gateway status: running"
        return 0
    else
        print_error "Gateway is NOT RUNNING"
        print_info "Status output: $gateway_status"
        log "WARN" "Gateway status: not running"
        return 1
    fi
}

# Check configuration file
check_config() {
    print_header "=== Configuration Check ==="
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        print_error "Config file missing: $CONFIG_FILE"
        log "ERROR" "Config file missing"
        return 1
    fi
    
    if is_valid_json "$CONFIG_FILE"; then
        print_success "Config file is valid JSON"
        log "INFO" "Config file valid"
        
        # Check for backups
        if [[ -f "${OPENCLAW_DIR}/openclaw.json.bak.1" ]]; then
            print_info "Backup file .bak.1 exists"
        fi
        if [[ -f "${OPENCLAW_DIR}/openclaw.json.bak.2" ]]; then
            print_info "Backup file .bak.2 exists"
        fi
        if [[ -f "${OPENCLAW_DIR}/openclaw.json.damaged" ]]; then
            print_warning "Damaged config file exists - may contain recoverable data"
        fi
        
        return 0
    else
        print_error "Config file is INVALID JSON"
        log "ERROR" "Config file invalid JSON"
        
        # Try to find valid backup
        for backup in "${BACKUP_FILES[@]}"; do
            if [[ -f "$backup" ]] && is_valid_json "$backup"; then
                print_info "Valid backup found: $backup"
                break
            fi
        done
        
        return 1
    fi
}

# Check disk space
check_disk() {
    print_header "=== Disk Space Check ==="
    
    local disk_usage
    disk_usage=$(df -h "$HOME" | tail -1 | awk '{print $5}' | sed 's/%//')
    
    print_info "Disk usage: ${disk_usage}%"
    
    if [[ "$disk_usage" -lt 80 ]]; then
        print_success "Disk space is OK"
        log "INFO" "Disk usage: ${disk_usage}%"
        return 0
    elif [[ "$disk_usage" -lt 90 ]]; then
        print_warning "Disk space is getting low (${disk_usage}%)"
        log "WARN" "Disk usage high: ${disk_usage}%"
        return 2
    else
        print_error "Disk space is CRITICAL (${disk_usage}%)"
        log "ERROR" "Disk usage critical: ${disk_usage}%"
        return 1
    fi
}

# Check workspaces
check_workspaces() {
    print_header "=== Workspace Check ==="
    
    local issues=0
    
    # Main workspace
    if [[ -d "$WORKSPACE_DIR" ]]; then
        print_success "Main workspace exists: $WORKSPACE_DIR"
        log "INFO" "Main workspace exists"
    else
        print_error "Main workspace MISSING: $WORKSPACE_DIR"
        log "ERROR" "Main workspace missing"
        ((issues++))
    fi
    
    # Dev workspace
    if [[ -d "$DEV_DIR" ]]; then
        print_success "Dev workspace exists: $DEV_DIR"
        log "INFO" "Dev workspace exists"
    else
        print_error "Dev workspace MISSING: $DEV_DIR"
        log "ERROR" "Dev workspace missing"
        ((issues++))
    fi
    
    # Extensions directory
    if [[ -d "$EXTENSIONS_DIR" ]]; then
        print_info "Extensions directory exists: $EXTENSIONS_DIR"
        log "INFO" "Extensions directory exists"
    else
        print_warning "Extensions directory MISSING: $EXTENSIONS_DIR"
        log "WARN" "Extensions directory missing"
    fi
    
    return $issues
}

# Check Node.js
check_node() {
    print_header "=== Node.js Check ==="
    
    if command_exists node; then
        local node_version
        node_version=$(node --version)
        print_success "Node.js available: $node_version"
        log "INFO" "Node.js version: $node_version"
        return 0
    else
        print_error "Node.js NOT FOUND"
        log "ERROR" "Node.js not found"
        return 1
    fi
}

# Check lock files
check_locks() {
    print_header "=== Lock Files Check ==="
    
    local lock_files
    lock_files=$(find "$OPENCLAW_DIR" -name "*.lock" -type f 2>/dev/null)
    
    if [[ -n "$lock_files" ]]; then
        print_warning "Found lock files:"
        echo "$lock_files" | while read -r lock; do
            print_info "  - $lock"
        done
        log "WARN" "Found lock files: $lock_files"
        return 1
    else
        print_success "No lock files found"
        log "INFO" "No lock files"
        return 0
    fi
}

# Check stuck processes
check_processes() {
    print_header "=== Process Check ==="
    
    local stuck_procs
    stuck_procs=$(pgrep -f "openclaw" 2>/dev/null || true)
    
    if [[ -n "$stuck_procs" ]]; then
        print_warning "Found OpenClaw processes:"
        echo "$stuck_procs" | while read -r pid; do
            local proc_info
            proc_info=$(ps -p "$pid" -o pid,cmd 2>/dev/null | tail -1 || echo "  PID: $pid")
            print_info "  $proc_info"
        done
        log "WARN" "Found OpenClaw processes: $stuck_procs"
        return 1
    else
        print_success "No stuck OpenClaw processes"
        log "INFO" "No stuck processes"
        return 0
    fi
}

# Run full diagnostic
run_diagnostic() {
    print_header "=========================================="
    print_header "  OpenClaw Diagnostic Report"
    print_header "=========================================="
    echo ""
    
    log "INFO" "Starting diagnostic run"
    
    local issues=0
    
    check_gateway || ((issues++))
    echo ""
    
    check_config || ((issues++))
    echo ""
    
    check_disk
    echo ""
    
    check_workspaces
    echo ""
    
    check_node
    echo ""
    
    check_locks || ((issues++))
    echo ""
    
    check_processes || ((issues++))
    echo ""
    
    print_header "=========================================="
    if [[ "$issues" -eq 0 ]]; then
        print_success "Diagnostic complete: No issues found"
        log "INFO" "Diagnostic complete: no issues"
        return 0
    else
        print_warning "Diagnostic complete: $issues issue(s) found"
        log "WARN" "Diagnostic complete: $issues issues found"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Fix Functions
# -----------------------------------------------------------------------------

# Fix Gateway
fix_openclaw_command() {
    print_header "=== Fix OpenClaw Command ==="
    
    log "INFO" "Checking OpenClaw command..."
    
    # Check if /usr/bin/env exists (the root cause of the issue)
    if [[ -x /usr/bin/env ]]; then
        print_success "/usr/bin/env exists - no fix needed"
        return 0
    fi
    
    print_warning "/usr/bin/env not found - creating workaround..."
    log "WARN" "Creating wrapper script to bypass missing /usr/bin/env"
    
    # The openclaw.mjs uses #!/usr/bin/env node which fails on Termux
    # We'll create a wrapper that calls node directly
    
    local openclaw_mjs="/data/data/com.termux/files/usr/lib/node_modules/openclaw/openclaw.mjs"
    local wrapper_path="/data/data/com.termux/files/usr/bin/openclaw-wrapper"
    
    # Check if the openclaw.mjs exists
    if [[ ! -f "$openclaw_mjs" ]]; then
        print_error "openclaw.mjs not found at: $openclaw_mjs"
        return 1
    fi
    
    # Check if node is available
    if ! command -v node &>/dev/null; then
        print_error "Node.js not found in PATH"
        return 1
    fi
    
    print_info "Creating wrapper script at: $wrapper_path"
    
    # Create the wrapper script
    cat > "$wrapper_path" << 'WRAPPER_EOF'
#!/bin/sh
# Wrapper script for openclaw - bypasses broken shebang
# Created by openclaw-recover.sh
exec node /data/data/com.termux/files/usr/lib/node_modules/openclaw/openclaw.mjs "$@"
WRAPPER_EOF
    
    # Make it executable
    chmod +x "$wrapper_path"
    
    if [[ -x "$wrapper_path" ]]; then
        print_success "Wrapper script created and executable"
        
        # Test the wrapper
        local test_result
        test_result=$("$wrapper_path" --version 2>&1) || true
        
        if echo "$test_result" | grep -qi "openclaw\|version"; then
            print_success "Wrapper works! Version: $test_result"
            
            # Backup original symlink and create new one
            if [[ -L /data/data/com.termux/files/usr/bin/openclaw ]]; then
                print_info "Backing up original symlink..."
                mv /data/data/com.termux/files/usr/bin/openclaw /data/data/com.termux/files/usr/bin/openclaw.broken
            fi
            
            # Create new symlink to wrapper
            print_info "Creating new symlink..."
            ln -sf "$wrapper_path" /data/data/com.termux/files/usr/bin/openclaw
            
            # Verify
            if openclaw --version &>/dev/null; then
                print_success "FIXED: openclaw command now works!"
                log "INFO" "OpenClaw command fixed via wrapper"
                return 0
            fi
        else
            print_error "Wrapper test failed: $test_result"
        fi
    fi
    
    print_error "Failed to create working wrapper"
    print_info "Manual fix: Add this to your PATH or use node directly"
    return 1
}

fix_gateway() {
    print_header "=== Fix Gateway ==="
    
    log "INFO" "Starting gateway fix"
    
    # First, check if openclaw command itself works
    if ! openclaw --version &>/dev/null; then
        print_error "OpenClaw command is broken - cannot proceed"
        print_info "Run with --fix-openclaw or manually fix: npm install -g openclaw"
        return 1
    fi
    
    # Step 1: Stop Gateway
    print_info "Stopping Gateway..."
    openclaw gateway stop 2>/dev/null || true
    sleep 1
    
    # Step 2: Kill stuck processes
    print_info "Killing stuck processes..."
    pkill -f "openclaw" 2>/dev/null || true
    pkill -f "node.*openclaw" 2>/dev/null || true
    
    # Step 3: Clear lock files
    print_info "Clearing lock files..."
    find "$OPENCLAW_DIR" -name "*.lock" -type f -delete 2>/dev/null || true
    
    # Step 4: Start Gateway fresh
    print_info "Starting Gateway..."
    openclaw gateway start
    
    # Step 5: Verify
    sleep 2
    if openclaw gateway status 2>&1 | grep -qi "running\|started\|active"; then
        print_success "Gateway restarted successfully"
        log "INFO" "Gateway fix successful"
        return 0
    else
        print_error "Gateway still not running - check logs"
        log "ERROR" "Gateway fix failed"
        return 1
    fi
}

# Fix Configuration
fix_config() {
    print_header "=== Fix Configuration ==="
    
    log "INFO" "Starting config fix"
    
    # First, make a backup of current config if it exists
    if [[ -f "$CONFIG_FILE" ]]; then
        local timestamp
        timestamp=$(date '+%Y%m%d_%H%M%S')
        cp "$CONFIG_FILE" "${CONFIG_FILE}.pre_recovery_${timestamp}"
        print_info "Backed up current config to .pre_recovery_${timestamp}"
    fi
    
    # Check each backup in priority order
    local restored=false
    
    # Try .bak.1 first
    if [[ -f "${OPENCLAW_DIR}/openclaw.json.bak.1" ]]; then
        print_info "Checking .bak.1..."
        if is_valid_json "${OPENCLAW_DIR}/openclaw.json.bak.1"; then
            print_success "Restoring from .bak.1"
            cp "${OPENCLAW_DIR}/openclaw.json.bak.1" "$CONFIG_FILE"
            restored=true
        fi
    fi
    
    # If .bak.1 didn't work, try .bak.2
    if [[ "$restored" == "false" && -f "${OPENCLAW_DIR}/openclaw.json.bak.2" ]]; then
        print_info "Checking .bak.2..."
        if is_valid_json "${OPENCLAW_DIR}/openclaw.json.bak.2"; then
            print_success "Restoring from .bak.2"
            cp "${OPENCLAW_DIR}/openclaw.json.bak.2" "$CONFIG_FILE"
            restored=true
        fi
    fi
    
    # If .bak.2 didn't work, try .damaged
    if [[ "$restored" == "false" && -f "${OPENCLAW_DIR}/openclaw.json.damaged" ]]; then
        print_info "Checking .damaged..."
        if is_valid_json "${OPENCLAW_DIR}/openclaw.json.damaged"; then
            if confirm_action "The .damaged file contains valid JSON. Restore it?"; then
                print_success "Restoring from .damaged"
                cp "${OPENCLAW_DIR}/openclaw.json.damaged" "$CONFIG_FILE"
                restored=true
            fi
        fi
    fi
    
    # Final validation
    if [[ "$restored" == "true" ]]; then
        if is_valid_json "$CONFIG_FILE"; then
            print_success "Config restored successfully"
            log "INFO" "Config restored from backup"
            
            # Restart gateway if needed
            print_info "Restarting Gateway to apply config changes..."
            openclaw gateway restart 2>/dev/null || openclaw gateway start 2>/dev/null || true
            return 0
        else
            print_error "Restored config is still invalid"
            log "ERROR" "Restored config invalid"
            return 1
        fi
    else
        print_error "No valid backup found"
        log "ERROR" "No valid config backup found"
        
        # Offer to create default config
        if confirm_action "Create default config file?"; then
            print_info "Creating default config..."
            cat > "$CONFIG_FILE" << 'EOF'
{
  "version": "1.0",
  "gateway": {
    "host": "localhost",
    "port": 3000
  },
  "agents": {
    "main": {
      "name": "MItermClaw",
      "model": "default"
    }
  },
  "plugins": {
    "entries": {},
    "installs": {}
  },
  "settings": {
    "maxSessions": 10,
    "logLevel": "info"
  }
}
EOF
            if is_valid_json "$CONFIG_FILE"; then
                print_success "Default config created"
                log "INFO" "Created default config"
                return 0
            fi
        fi
        
        return 1
    fi
}

# Create backups
create_backup() {
    print_header "=== Create Backups ==="
    
    log "INFO" "Starting backup"
    
    local timestamp
    timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_dir="${HOME}/openclaw-backups/${timestamp}"
    
    # Ensure backup directory exists
    mkdir -p "$backup_dir"
    print_info "Backup directory: $backup_dir"
    
    # Backup workspace
    if [[ -d "$WORKSPACE_DIR" ]]; then
        local ws_backup="${backup_dir}/workspace.tar.gz"
        print_info "Backing up workspace..."
        tar -czf "$ws_backup" -C "$OPENCLAW_DIR" workspace 2>/dev/null && \
            print_success "Workspace backed up" || \
            print_warning "Workspace backup failed"
    fi
    
    # Backup config
    if [[ -f "$CONFIG_FILE" ]]; then
        local cfg_backup="${backup_dir}/config.json"
        print_info "Backing up config..."
        cp "$CONFIG_FILE" "$cfg_backup" && \
            print_success "Config backed up" || \
            print_warning "Config backup failed"
    fi
    
    # Backup dev workspace
    if [[ -d "$DEV_DIR" ]]; then
        local dev_backup="${backup_dir}/dev-workspace.tar.gz"
        print_info "Backing up dev workspace..."
        tar -czf "$dev_backup" -C "$HOME" openclaw-dev 2>/dev/null && \
            print_success "Dev workspace backed up" || \
            print_warning "Dev workspace backup failed"
    fi
    
    # Backup extensions
    if [[ -d "$EXTENSIONS_DIR" ]]; then
        local ext_backup="${backup_dir}/extensions.tar.gz"
        print_info "Backing up extensions..."
        tar -czf "$ext_backup" -C "$OPENCLAW_DIR" extensions 2>/dev/null && \
            print_success "Extensions backed up" || \
            print_warning "Extensions backup failed"
    fi
    
    # Create manifest
    cat > "${backup_dir}/manifest.txt" << EOF
OpenClaw Backup Manifest
=========================
Created: $(date)
Timestamp: $timestamp

Contents:
$(ls -la "$backup_dir" | grep -v "^d" | tail -n +2)

Backed up paths:
- Config: $CONFIG_FILE
- Workspace: $WORKSPACE_DIR
- Dev workspace: $DEV_DIR
- Extensions: $EXTENSIONS_DIR
EOF

    print_success "Backup complete: $backup_dir"
    log "INFO" "Backup complete: $backup_dir"
    
    # Display backup summary
    print_info "Backup summary:"
    du -sh "$backup_dir" 2>/dev/null || true
    
    return 0
}

# Run all fix procedures
fix_all() {
    print_header "=========================================="
    print_header "  Running All Fix Procedures"
    print_header "=========================================="
    echo ""
    
    log "INFO" "Starting fix-all procedure"
    
    # First run diagnostic to see what needs fixing
    print_info "Running diagnostic first..."
    run_diagnostic
    echo ""
    
    # Fix config first (gateway depends on it)
    print_info "=== Step 1: Fix Configuration ==="
    fix_config
    echo ""
    
    # Fix gateway
    print_info "=== Step 2: Fix Gateway ==="
    fix_gateway
    echo ""
    
    # Verify everything is working
    print_info "=== Verification ==="
    run_diagnostic
    
    print_header "=========================================="
    print_success "All fix procedures complete"
    log "INFO" "fix-all complete"
    
    return 0
}

# -----------------------------------------------------------------------------
# Help & Usage
# -----------------------------------------------------------------------------

show_help() {
    cat << EOF
OpenClaw Recovery Script
========================

Usage: $(basename "$0") [OPTIONS]

OPTIONS:
    -d, --diagnostic       Run full health check (gateway, config, disk, workspaces)
    -g, --fix-gateway      Restart gateway, clear locks, kill stuck processes
    -c, --fix-config       Restore config from backup (checks .bak.1, .bak.2, .damaged)
    -o, --fix-openclaw     Fix broken openclaw command (missing /usr/bin/env)
    -a, --fix-all          Run all fix procedures
    -b, --backup           Create timestamped backups of workspace, config, dev-workspace
    -y, --yes              Skip confirmation prompts for destructive operations
    -v, --verbose         Enable verbose output
    -h, --help             Show this help message

EXAMPLES:
    # Run diagnostic to see what's broken
    $(basename "$0") --diagnostic

    # Fix gateway issues
    $(basename "$0") --fix-gateway

    # Restore config from backup
    $(basename "$0") --fix-config

    # Run all fixes
    $(basename "$0") --fix-all --yes

    # Create backup
    $(basename "$0") --backup

KEY PATHS:
    Config:       $CONFIG_FILE
    Main workspace: $WORKSPACE_DIR
    Dev workspace: $DEV_DIR
    Extensions:   $EXTENSIONS_DIR
    Logs:         $LOGS_DIR

BACKUP FILES:
    $CONFIG_FILE.bak.1
    $CONFIG_FILE.bak.2
    $CONFIG_FILE.damaged

LOG FILE:
    $RECOVERY_LOG

NOTES:
    - The script is idempotent - safe to run multiple times
    - All actions are logged to $RECOVERY_LOG
    - Use --yes or -y to skip confirmation prompts

EOF
}

# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------

main() {
    # Parse arguments
    local mode=""
    
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--diagnostic)
                mode="diagnostic"
                ;;
            -g|--fix-gateway)
                mode="fix-gateway"
                ;;
            -c|--fix-config)
                mode="fix-config"
                ;;
            -o|--fix-openclaw)
                mode="fix-openclaw"
                ;;
            -a|--fix-all)
                mode="fix-all"
                ;;
            -b|--backup)
                mode="backup"
                ;;
            -y|--yes)
                FORCE_YES=true
                ;;
            -v|--verbose)
                VERBOSE=true
                ;;
            -h|--help)
                mode="help"
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
        shift
    done
    
    # If no mode specified, show help
    if [[ -z "$mode" ]]; then
        show_help
        exit 0
    fi
    
    # Execute requested mode
    case "$mode" in
        diagnostic)
            run_diagnostic
            exit $?
            ;;
        fix-gateway)
            if [[ "$FORCE_YES" == "false" ]]; then
                if ! confirm_action "This will restart the gateway. Continue?"; then
                    print_info "Cancelled"
                    exit 0
                fi
            fi
            fix_gateway
            exit $?
            ;;
        fix-config)
            if [[ "$FORCE_YES" == "false" ]]; then
                if ! confirm_action "This will restore config from backup. Continue?"; then
                    print_info "Cancelled"
                    exit 0
                fi
            fi
            fix_config
            exit $?
            ;;
        fix-openclaw)
            if [[ "$FORCE_YES" == "false" ]]; then
                if ! confirm_action "This will fix the broken openclaw command. Continue?"; then
                    print_info "Cancelled"
                    exit 0
                fi
            fi
            fix_openclaw_command
            exit $?
            ;;
        fix-all)
            if [[ "$FORCE_YES" == "false" ]]; then
                if ! confirm_action "This will run all fix procedures. Continue?"; then
                    print_info "Cancelled"
                    exit 0
                fi
            fi
            fix_all
            exit $?
            ;;
        backup)
            create_backup
            exit $?
            ;;
        help)
            show_help
            exit 0
            ;;
    esac
}

# Run main function
main "$@"