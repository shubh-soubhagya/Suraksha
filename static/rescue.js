class RescueTeamPortal {
    constructor() {
        this.members = [];
        this.currentLocation = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadMembersFromServer();
    }

    bindEvents() {
        // Registration form
        document.getElementById('registrationForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegistration();
        });

        // Location button
        document.getElementById('getLocationBtn').addEventListener('click', () => {
            this.getCurrentLocation();
        });

        // Toggle view button
        document.getElementById('toggleViewBtn').addEventListener('click', () => {
            this.toggleView();
        });

        // Search and filter
        document.getElementById('searchInput').addEventListener('input', () => {
            this.filterMembers();
        });

        document.getElementById('filterSpecialization').addEventListener('change', () => {
            this.filterMembers();
        });
    }

    async loadMembersFromServer() {
        try {
            const response = await fetch('/api/rescue/members');
            const data = await response.json();
            this.members = data.members || [];
            this.renderMembers();
            this.updateMemberCount();
        } catch (error) {
            console.error('Error loading members:', error);
        }
    }

    async getCurrentLocation() {
        const statusDiv = document.getElementById('locationStatus');
        const locationBtn = document.getElementById('getLocationBtn');
        
        locationBtn.textContent = '📍 Getting Location...';
        locationBtn.disabled = true;

        if (!navigator.geolocation) {
            this.showLocationStatus('Geolocation is not supported by this browser.', 'error');
            locationBtn.textContent = '📍 Get Current Location';
            locationBtn.disabled = false;
            return;
        }

        const options = {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        };

        navigator.geolocation.getCurrentPosition(
            (position) => {
                this.currentLocation = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                };
                
                this.showLocationStatus(
                    `✅ Location obtained successfully! (Accuracy: ${Math.round(position.coords.accuracy)}m)`,
                    'success'
                );
                
                locationBtn.textContent = '📍 Location Obtained';
                locationBtn.disabled = false;
            },
            (error) => {
                let message = 'Unable to get location. ';
                switch(error.code) {
                    case error.PERMISSION_DENIED:
                        message += 'Location access denied by user.';
                        break;
                    case error.POSITION_UNAVAILABLE:
                        message += 'Location information unavailable.';
                        break;
                    case error.TIMEOUT:
                        message += 'Location request timed out.';
                        break;
                    default:
                        message += 'An unknown error occurred.';
                        break;
                }
                
                this.showLocationStatus(message, 'error');
                locationBtn.textContent = '📍 Get Current Location';
                locationBtn.disabled = false;
            },
            options
        );
    }

    showLocationStatus(message, type) {
        const statusDiv = document.getElementById('locationStatus');
        statusDiv.textContent = message;
        statusDiv.className = `location-status ${type}`;
    }

    async handleRegistration() {
        const form = document.getElementById('registrationForm');
        const formData = new FormData(form);
        
        // Validate required fields
        const requiredFields = ['name', 'phone', 'email', 'deptId'];
        for (let field of requiredFields) {
            if (!formData.get(field).trim()) {
                this.showError(`Please fill in the ${field} field.`);
                return;
            }
        }

        // Validate location
        if (!this.currentLocation) {
            this.showError('Please get your current location before registering.');
            return;
        }

        // Create new member object
        const memberData = {
            name: formData.get('name').trim(),
            phone: formData.get('phone').trim(),
            email: formData.get('email').trim(),
            deptId: formData.get('deptId').trim(),
            specialization: formData.get('specialization') || 'general',
            location: this.currentLocation
        };

        try {
            const response = await fetch('/api/rescue/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(memberData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showSuccess('Registration successful! You have been added to the rescue team database.');
                form.reset();
                this.currentLocation = null;
                document.getElementById('locationStatus').textContent = '';
                document.getElementById('getLocationBtn').textContent = '📍 Get Current Location';
                await this.loadMembersFromServer();
            } else {
                this.showError(result.error || 'Registration failed');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.showError('Registration failed. Please try again.');
        }
    }

    showError(message) {
        const form = document.getElementById('registrationForm');
        
        // Remove existing error messages
        const existingError = form.querySelector('.error-message');
        if (existingError) {
            existingError.remove();
        }

        // Create error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.style.cssText = `
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #dc3545;
        `;
        errorDiv.textContent = message;

        form.insertBefore(errorDiv, form.firstChild);
        form.classList.add('shake');
        setTimeout(() => form.classList.remove('shake'), 500);

        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }

    showSuccess(message) {
        const form = document.getElementById('registrationForm');
        
        const existingMessage = form.querySelector('.success-message, .error-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        const successDiv = document.createElement('div');
        successDiv.className = 'success-message';
        successDiv.style.cssText = `
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #28a745;
        `;
        successDiv.textContent = message;

        form.insertBefore(successDiv, form.firstChild);

        setTimeout(() => {
            if (successDiv.parentNode) {
                successDiv.remove();
            }
        }, 5000);
    }

    toggleView() {
        const registrationSection = document.getElementById('registrationSection');
        const membersSection = document.getElementById('membersSection');
        const toggleBtn = document.getElementById('toggleViewBtn');

        if (membersSection.style.display === 'none') {
            membersSection.style.display = 'block';
            registrationSection.style.display = 'none';
            toggleBtn.textContent = 'Back to Registration';
            this.renderMembers();
        } else {
            membersSection.style.display = 'none';
            registrationSection.style.display = 'block';
            toggleBtn.textContent = 'View Rescue Team Members';
        }
    }

    filterMembers() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const filterSpec = document.getElementById('filterSpecialization').value;
        
        const filteredMembers = this.members.filter(member => {
            const matchesSearch = member.name.toLowerCase().includes(searchTerm) ||
                                member.specialization.toLowerCase().includes(searchTerm) ||
                                member.deptId.toLowerCase().includes(searchTerm);
            
            const matchesFilter = !filterSpec || member.specialization === filterSpec;
            
            return matchesSearch && matchesFilter;
        });

        this.renderMembers(filteredMembers);
    }

    renderMembers(membersToRender = this.members) {
        const membersList = document.getElementById('membersList');
        
        if (membersToRender.length === 0) {
            membersList.innerHTML = '<div class="no-members">No rescue team members found.</div>';
            return;
        }

        membersList.innerHTML = membersToRender.map(member => {
            let distanceText = '';
            if (member.distance !== undefined) {
                distanceText = `<div class="detail-item"><strong>Distance:</strong> <span class="distance">${member.distance} km away</span></div>`;
            }

            const specializationDisplay = member.specialization.charAt(0).toUpperCase() + member.specialization.slice(1);

            return `
                <div class="member-card">
                    <div class="member-header">
                        <h3 class="member-name">${member.name}</h3>
                        <span class="dept-id">ID: ${member.deptId}</span>
                    </div>
                    <div class="member-details">
                        <div class="detail-item"><strong>Phone:</strong> ${member.phone}</div>
                        <div class="detail-item"><strong>Email:</strong> ${member.email}</div>
                        ${distanceText}
                        <div class="specialization-tag">${specializationDisplay} Specialist</div>
                    </div>
                    <button class="call-btn" onclick="window.open('tel:${member.phone}')">
                        📞 Call Now
                    </button>
                </div>
            `;
        }).join('');
    }

    updateMemberCount() {
        const count = this.members.length;
        const toggleBtn = document.getElementById('toggleViewBtn');
        
        if (count > 0) {
            toggleBtn.textContent = `View Rescue Team Members (${count})`;
        } else {
            toggleBtn.textContent = 'View Rescue Team Members';
        }
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new RescueTeamPortal();
});
