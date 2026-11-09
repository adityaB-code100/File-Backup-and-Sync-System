"""
VaultCloud Supported Locations Dataset for backend validation.
Matches frontend/src/data/locations.js
"""

SUPPORTED_COUNTRIES = [
    'India',
    'United States',
    'United Kingdom',
    'Canada'
]

LOCATION_DATA = {
    'India': {
        'Andhra Pradesh': [
            'Visakhapatnam', 'Vijayawada', 'Guntur', 'Nellore', 'Kurnool',
            'Rajahmundry', 'Tirupati', 'Kakinada', 'Kadapa', 'Anantapur'
        ],
        'Arunachal Pradesh': [
            'Itanagar', 'Naharlagun', 'Pasighat', 'Tawang', 'Ziro'
        ],
        'Assam': [
            'Guwahati', 'Silchar', 'Dibrugarh', 'Jorhat', 'Nagaon', 'Tinsukia', 'Tezpur'
        ],
        'Bihar': [
            'Patna', 'Gaya', 'Bhagalpur', 'Muzaffarpur', 'Purnia', 'Darbhanga', 'Bihar Sharif', 'Arrah'
        ],
        'Chhattisgarh': [
            'Raipur', 'Bhilai', 'Bilaspur', 'Korba', 'Rajnandgaon', 'Durg', 'Jagdalpur'
        ],
        'Goa': [
            'Panaji', 'Margao', 'Vasco da Gama', 'Mapusa', 'Ponda'
        ],
        'Gujarat': [
            'Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Bhavnagar', 'Jamnagar',
            'Junagadh', 'Gandhinagar', 'Anand', 'Navsari'
        ],
        'Haryana': [
            'Faridabad', 'Gurugram', 'Panipat', 'Ambala', 'Yamunanagar', 'Rohtak',
            'Hisar', 'Karnal', 'Sonipat', 'Panchkula'
        ],
        'Himachal Pradesh': [
            'Shimla', 'Dharamshala', 'Solan', 'Mandi', 'Kullu', 'Manali', 'Baddi'
        ],
        'Jharkhand': [
            'Ranchi', 'Jamshedpur', 'Dhanbad', 'Bokaro', 'Deoghar', 'Hazaribagh'
        ],
        'Karnataka': [
            'Bengaluru', 'Mysuru', 'Hubballi-Dharwad', 'Mangaluru', 'Belagavi',
            'Davanagere', 'Ballari', 'Kalaburagi', 'Shivamogga', 'Udupi'
        ],
        'Kerala': [
            'Thiruvananthapuram', 'Kochi', 'Kozhikode', 'Kollam', 'Thrissur',
            'Alappuzha', 'Palakkad', 'Kannur', 'Kottayam'
        ],
        'Madhya Pradesh': [
            'Indore', 'Bhopal', 'Jabalpur', 'Gwalior', 'Ujjain', 'Sagar', 'Dewas', 'Satna'
        ],
        'Maharashtra': [
            'Nanded', 'Mumbai', 'Pune', 'Nagpur', 'Nashik',
            'Chhatrapati Sambhaji Nagar (Aurangabad)', 'Thane', 'Solapur', 'Amravati',
            'Kolhapur', 'Navi Mumbai', 'Latur', 'Jalgaon', 'Akola', 'Dhule',
            'Ahmednagar', 'Chandrapur', 'Parbhani', 'Satara', 'Sangli'
        ],
        'Manipur': [
            'Imphal', 'Churachandpur', 'Thoubal', 'Bishnupur', 'Ukhrul'
        ],
        'Meghalaya': [
            'Shillong', 'Tura', 'Jowai', 'Nongstoin', 'Cherrapunji'
        ],
        'Mizoram': [
            'Aizawl', 'Lunglei', 'Champhai', 'Serchhip', 'Kolasib'
        ],
        'Nagaland': [
            'Kohima', 'Dimapur', 'Mokokchung', 'Tuensang', 'Wokha'
        ],
        'Odisha': [
            'Bhubaneswar', 'Cuttack', 'Rourkela', 'Berhampur', 'Sambalpur', 'Puri', 'Balasore'
        ],
        'Punjab': [
            'Ludhiana', 'Amritsar', 'Jalandhar', 'Patiala', 'Bathinda', 'Mohali', 'Pathankot'
        ],
        'Rajasthan': [
            'Jaipur', 'Jodhpur', 'Kota', 'Bikaner', 'Ajmer', 'Udaipur', 'Bhilwara', 'Alwar', 'Sikar'
        ],
        'Sikkim': [
            'Gangtok', 'Namchi', 'Geyzing', 'Mangan', 'Pelling'
        ],
        'Tamil Nadu': [
            'Chennai', 'Coimbatore', 'Madurai', 'Tiruchirappalli', 'Salem',
            'Tirunelveli', 'Tiruppur', 'Vellore', 'Erode', 'Thoothukudi'
        ],
        'Telangana': [
            'Hyderabad', 'Warangal', 'Nizamabad', 'Karimnagar', 'Ramagundam', 'Khammam', 'Nalgonda'
        ],
        'Tripura': [
            'Agartala', 'Dharmanagar', 'Udaipur', 'Kailashahar', 'Belonia'
        ],
        'Uttar Pradesh': [
            'Lucknow', 'Kanpur', 'Varanasi', 'Agra', 'Prayagraj', 'Meerut',
            'Ghaziabad', 'Noida', 'Bareilly', 'Aligarh', 'Moradabad', 'Gorakhpur', 'Mathura', 'Ayodhya'
        ],
        'Uttarakhand': [
            'Dehradun', 'Haridwar', 'Roorkee', 'Haldwani', 'Rudrapur', 'Rishikesh', 'Nainital'
        ],
        'West Bengal': [
            'Kolkata', 'Howrah', 'Durgapur', 'Asansol', 'Siliguri', 'Bardhaman', 'Malda', 'Kharagpur'
        ],
        'Andaman and Nicobar Islands': [
            'Port Blair', 'Diglipur', 'Mayabunder'
        ],
        'Chandigarh': [
            'Chandigarh'
        ],
        'Dadra and Nagar Haveli and Daman and Diu': [
            'Daman', 'Diu', 'Silvassa'
        ],
        'Delhi': [
            'New Delhi', 'North Delhi', 'South Delhi', 'East Delhi', 'West Delhi', 'Central Delhi', 'Dwarka', 'Rohini'
        ],
        'Jammu and Kashmir': [
            'Srinagar', 'Jammu', 'Anantnag', 'Baramulla', 'Udhampur', 'Kathua'
        ],
        'Ladakh': [
            'Leh', 'Kargil'
        ],
        'Lakshadweep': [
            'Kavaratti', 'Agatti', 'Amini', 'Andrott'
        ],
        'Puducherry': [
            'Puducherry', 'Karaikal', 'Mahe', 'Yanam'
        ]
    },
    'United States': {
        'California': [
            'Los Angeles', 'San Francisco', 'San Diego', 'San Jose', 'Fresno',
            'Sacramento', 'Long Beach', 'Oakland', 'Bakersfield', 'Anaheim', 'Santa Ana', 'Riverside', 'Irvine'
        ],
        'New York': [
            'New York City', 'Buffalo', 'Rochester', 'Yonkers', 'Syracuse', 'Albany'
        ],
        'Texas': [
            'Houston', 'San Antonio', 'Dallas', 'Austin', 'Fort Worth', 'El Paso', 'Arlington'
        ],
        'Florida': [
            'Miami', 'Orlando', 'Tampa', 'Jacksonville', 'St. Petersburg', 'Tallahassee', 'Fort Lauderdale'
        ],
        'Illinois': [
            'Chicago', 'Aurora', 'Naperville', 'Joliet', 'Rockford', 'Springfield'
        ],
        'Washington': [
            'Seattle', 'Spokane', 'Tacoma', 'Vancouver', 'Bellevue', 'Everett', 'Olympia'
        ],
        'Massachusetts': [
            'Boston', 'Worcester', 'Springfield', 'Cambridge', 'Lowell', 'Brockton'
        ],
        'Pennsylvania': [
            'Philadelphia', 'Pittsburgh', 'Allentown', 'Erie', 'Reading', 'Scranton', 'Harrisburg'
        ],
        'Georgia': [
            'Atlanta', 'Augusta', 'Columbus', 'Macon', 'Savannah', 'Athens'
        ],
        'North Carolina': [
            'Charlotte', 'Raleigh', 'Greensboro', 'Durham', 'Winston-Salem', 'Fayetteville'
        ],
        'Ohio': [
            'Columbus', 'Cleveland', 'Cincinnati', 'Toledo', 'Akron', 'Dayton'
        ],
        'Michigan': [
            'Detroit', 'Grand Rapids', 'Warren', 'Sterling Heights', 'Ann Arbor', 'Lansing'
        ],
        'Colorado': [
            'Denver', 'Colorado Springs', 'Aurora', 'Fort Collins', 'Lakewood', 'Boulder'
        ],
        'Arizona': [
            'Phoenix', 'Tucson', 'Mesa', 'Chandler', 'Scottsdale', 'Glendale', 'Tempe'
        ],
        'Virginia': [
            'Virginia Beach', 'Norfolk', 'Chesapeake', 'Richmond', 'Newport News', 'Alexandria'
        ],
        'New Jersey': [
            'Newark', 'Jersey City', 'Paterson', 'Elizabeth', 'Trenton', 'Camden'
        ],
        'District of Columbia': [
            'Washington'
        ],
        'Oregon': [
            'Portland', 'Salem', 'Eugene', 'Gresham', 'Hillsboro', 'Beaverton', 'Bend'
        ],
        'Nevada': [
            'Las Vegas', 'Henderson', 'Reno', 'North Las Vegas', 'Sparks', 'Carson City'
        ],
        'Indiana': [
            'Indianapolis', 'Fort Wayne', 'Evansville', 'South Bend', 'Carmel'
        ],
        'Tennessee': [
            'Nashville', 'Memphis', 'Knoxville', 'Chattanooga', 'Clarksville'
        ],
        'Missouri': [
            'Kansas City', 'St. Louis', 'Springfield', 'Columbia', 'Independence'
        ],
        'Maryland': [
            'Baltimore', 'Frederick', 'Rockville', 'Gaithersburg', 'Annapolis'
        ],
        'Wisconsin': [
            'Milwaukee', 'Madison', 'Green Bay', 'Kenosha', 'Racine'
        ],
        'Minnesota': [
            'Minneapolis', 'Saint Paul', 'Rochester', 'Duluth', 'Bloomington'
        ],
        'South Carolina': [
            'Charleston', 'Columbia', 'North Charleston', 'Mount Pleasant', 'Greenville'
        ],
        'Alabama': [
            'Huntsville', 'Birmingham', 'Montgomery', 'Mobile', 'Tuscaloosa'
        ],
        'Louisiana': [
            'New Orleans', 'Baton Rouge', 'Shreveport', 'Lafayette', 'Lake Charles'
        ],
        'Kentucky': [
            'Louisville', 'Lexington', 'Bowling Green', 'Owensboro', 'Covington'
        ],
        'Utah': [
            'Salt Lake City', 'West Valley City', 'Provo', 'West Jordan', 'Orem'
        ],
        'Oklahoma': [
            'Oklahoma City', 'Tulsa', 'Norman', 'Broken Arrow', 'Edmond'
        ],
        'Connecticut': [
            'Bridgeport', 'Stamford', 'New Haven', 'Hartford', 'Waterbury'
        ],
        'Iowa': [
            'Des Moines', 'Cedar Rapids', 'Davenport', 'Sioux City', 'Iowa City'
        ],
        'Mississippi': [
            'Jackson', 'Gulfport', 'Southaven', 'Biloxi', 'Hattiesburg'
        ],
        'Arkansas': [
            'Little Rock', 'Fayetteville', 'Fort Smith', 'Springdale', 'Jonesboro'
        ],
        'Kansas': [
            'Wichita', 'Overland Park', 'Kansas City', 'Olathe', 'Topeka'
        ],
        'New Mexico': [
            'Albuquerque', 'Las Cruces', 'Rio Rancho', 'Santa Fe', 'Roswell'
        ],
        'Nebraska': [
            'Omaha', 'Lincoln', 'Bellevue', 'Grand Island', 'Kearney'
        ],
        'Idaho': [
            'Boise', 'Meridian', 'Nampa', 'Idaho Falls', 'Caldwell'
        ],
        'West Virginia': [
            'Charleston', 'Huntington', 'Morgantown', 'Parkersburg', 'Wheeling'
        ],
        'Hawaii': [
            'Honolulu', 'East Honolulu', 'Pearl City', 'Hilo', 'Kailua'
        ],
        'New Hampshire': [
            'Manchester', 'Nashua', 'Concord', 'Dover', 'Rochester'
        ],
        'Maine': [
            'Portland', 'Lewiston', 'Bangor', 'South Portland', 'Auburn'
        ],
        'Rhode Island': [
            'Providence', 'Warwick', 'Cranston', 'Pawtucket', 'East Providence'
        ],
        'Montana': [
            'Billings', 'Missoula', 'Great Falls', 'Bozeman', 'Helena'
        ],
        'Delaware': [
            'Wilmington', 'Dover', 'Newark', 'Middletown', 'Smyrna'
        ],
        'South Dakota': [
            'Sioux Falls', 'Rapid City', 'Aberdeen', 'Brookings', 'Watertown'
        ],
        'North Dakota': [
            'Fargo', 'Bismarck', 'Grand Forks', 'Minot', 'West Fargo'
        ],
        'Alaska': [
            'Anchorage', 'Fairbanks', 'Juneau', 'Wasilla', 'Sitka'
        ],
        'Vermont': [
            'Burlington', 'South Burlington', 'Rutland', 'Barre', 'Montpelier'
        ],
        'Wyoming': [
            'Cheyenne', 'Casper', 'Laramie', 'Gillette', 'Rock Springs'
        ]
    },
    'United Kingdom': {
        'England': [
            'London', 'Birmingham', 'Manchester', 'Liverpool', 'Leeds', 'Sheffield',
            'Bristol', 'Newcastle upon Tyne', 'Nottingham', 'Leicester', 'Southampton',
            'Portsmouth', 'Oxford', 'Cambridge', 'Brighton', 'Bath', 'York', 'Norwich'
        ],
        'Scotland': [
            'Edinburgh', 'Glasgow', 'Aberdeen', 'Dundee', 'Inverness', 'Stirling', 'Perth', 'St Andrews'
        ],
        'Wales': [
            'Cardiff', 'Swansea', 'Newport', 'Wrexham', 'Bangor', 'St Davids', 'Aberystwyth'
        ],
        'Northern Ireland': [
            'Belfast', 'Derry (Londonderry)', 'Lisburn', 'Newry', 'Armagh', 'Bangor', 'Coleraine'
        ]
    },
    'Canada': {
        'Ontario': [
            'Toronto', 'Ottawa', 'Mississauga', 'Brampton', 'Hamilton', 'London',
            'Markham', 'Vaughan', 'Kitchener', 'Windsor', 'Burlington', 'Greater Sudbury', 'Oshawa', 'Barrie'
        ],
        'Quebec': [
            'Montreal', 'Quebec City', 'Laval', 'Gatineau', 'Longueuil', 'Sherbrooke', 'Saguenay', 'Levis'
        ],
        'British Columbia': [
            'Vancouver', 'Victoria', 'Surrey', 'Burnaby', 'Richmond', 'Kelowna', 'Abbotsford', 'Nanaimo'
        ],
        'Alberta': [
            'Calgary', 'Edmonton', 'Red Deer', 'Lethbridge', 'St. Albert', 'Medicine Hat'
        ],
        'Manitoba': [
            'Winnipeg', 'Brandon', 'Steinbach', 'Thompson', 'Portage la Prairie'
        ],
        'Saskatchewan': [
            'Saskatoon', 'Regina', 'Prince Albert', 'Moose Jaw', 'Swift Current'
        ],
        'Nova Scotia': [
            'Halifax', 'Sydney', 'Dartmouth', 'Truro', 'New Glasgow'
        ],
        'New Brunswick': [
            'Moncton', 'Saint John', 'Fredericton', 'Dieppe', 'Miramichi'
        ],
        'Newfoundland and Labrador': [
            "St. John's", 'Mount Pearl', 'Corner Brook', 'Conception Bay South'
        ],
        'Prince Edward Island': [
            'Charlottetown', 'Summerside', 'Stratford', 'Cornwall'
        ],
        'Northwest Territories': [
            'Yellowknife', 'Inuvik', 'Hay River'
        ],
        'Yukon': [
            'Whitehorse', 'Dawson City', 'Watson Lake'
        ],
        'Nunavut': [
            'Iqaluit', 'Rankin Inlet', 'Arviat'
        ]
    }
}


def validate_location(country: str, state: str, city: str):
    """
    Validates country -> state -> city relationship against LOCATION_DATA.
    Returns (is_valid, error_message).
    All fields are optional, but if provided, must be valid and coherent.
    """
    country = country.strip() if country else ''
    state = state.strip() if state else ''
    city = city.strip() if city else ''

    if not country:
        if state:
            return False, "Cannot select a state without selecting a country."
        if city:
            return False, "Cannot select a city without selecting a country and state."
        return True, ""

    if country not in SUPPORTED_COUNTRIES:
        return False, f"Country '{country}' is not supported. Supported countries are: {', '.join(SUPPORTED_COUNTRIES)}."

    country_states = LOCATION_DATA.get(country, {})

    if not state:
        if city:
            return False, "Cannot select a city without selecting a state."
        return True, ""

    if state not in country_states:
        return False, f"State/Province '{state}' is not a valid state for {country}."

    if not city:
        return True, ""

    state_cities = country_states.get(state, [])
    # Case-insensitive check or direct match
    match_found = any(c.lower() == city.lower() for c in state_cities)
    if not match_found:
        return False, f"City '{city}' is not in the supported location list for {state}, {country}."

    return True, ""

