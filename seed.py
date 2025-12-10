from app import app, db, Rate

def seed():
    with app.app_context():
        db.create_all()
        
        if not Rate.query.filter_by(vehicle_type='Auto').first():
            db.session.add(Rate(vehicle_type='Auto', hourly_rate=20.0))
            print("Added Auto rate: $20")
            
        if not Rate.query.filter_by(vehicle_type='Moto').first():
            db.session.add(Rate(vehicle_type='Moto', hourly_rate=10.0))
            print("Added Moto rate: $10")
            
        db.session.commit()
        print("Database seeded!")

if __name__ == '__main__':
    seed()
