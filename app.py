from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key_here'  # Required for session management
db = SQLAlchemy(app)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    todos = db.relationship('Todo', backref='category', lazy=True, cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f"{self.name}"

class Todo(db.Model):
    sno = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    desc = db.Column(db.String(500), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    priority = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)

    def __repr__(self) -> str:
        return f"{self.sno} - {self.title}"
    
@app.route('/', methods=['GET', 'POST'])
def hello_world():
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['desc']
        category_id = request.form.get('category_id')
        category_id = int(category_id) if category_id else None
        # Get max priority and set new todo's priority higher
        max_priority = db.session.query(db.func.max(Todo.priority)).scalar() or 0
        todo = Todo(title=title, desc=desc, priority=max_priority + 1, category_id=category_id)
        db.session.add(todo)
        db.session.commit()

    # Get filter parameter from query string
    selected_category = request.args.get('category')

    # Get all categories ordered by name
    all_categories = Category.query.order_by(Category.name).all()

    # Default list (no filter)
    allTodo = Todo.query.order_by(Todo.priority).all()
    selected_category_id = None
    selected_category_name = None

    if selected_category and selected_category != 'all':
        try:
            category_id = int(selected_category)
        except ValueError:
            category_id = None

        if category_id is not None:
            category_obj = Category.query.get(category_id)
            if category_obj:
                selected_category_id = category_id
                selected_category_name = category_obj.name
                allTodo = Todo.query.filter_by(category_id=category_id).order_by(Todo.priority).all()

    return render_template(
        'index.html',
        allTodo=allTodo,
        all_categories=all_categories,
        selected_category=selected_category,
        selected_category_id=selected_category_id,
        selected_category_name=selected_category_name,
    )

@app.route('/update/<int:sno>', methods=['GET', 'POST'])
def update(sno):
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['desc']
        category_id = request.form.get('category_id')
        category_id = int(category_id) if category_id else None
        todo = Todo.query.filter_by(sno=sno).first()
        todo.title = title
        todo.desc = desc
        todo.category_id = category_id
        db.session.add(todo)
        db.session.commit()
        return redirect("/")

    todo = Todo.query.filter_by(sno=sno).first()
    all_categories = Category.query.all()
    return render_template('update.html', todo=todo, all_categories=all_categories)

@app.route('/delete/<int:sno>')
def delete(sno):
    todo = Todo.query.filter_by(sno=sno).first()
    db.session.delete(todo)
    db.session.commit()
    return redirect("/")

@app.route('/toggle_complete/<int:sno>', methods=['POST'])
def toggle_complete(sno):
    todo = Todo.query.filter_by(sno=sno).first_or_404()
    todo.completed = not todo.completed
    db.session.commit()
    selected_category = request.args.get('category', 'all')
    return redirect(f"/?category={selected_category}")

@app.route('/change_priority', methods=['GET', 'POST'])
def change_priority():
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Initialize session priority data if not already done
        if 'temp_priorities' not in session:
            # Load current priorities from database
            all_todos = Todo.query.all()
            session['temp_priorities'] = {str(todo.sno): todo.priority for todo in all_todos}
        
        if action == 'confirm':
            # Handle new order from drag-and-drop
            new_order = request.form.get('new_order', '')
            
            if new_order:
                # New order received from drag-and-drop
                sno_list = [int(sno) for sno in new_order.split(',') if sno]
                for index, sno in enumerate(sno_list):
                    todo = Todo.query.filter_by(sno=sno).first()
                    if todo:
                        todo.priority = index + 1
            else:
                # Fall back to temporary priorities from session (for up/down buttons)
                temp_priorities = session.get('temp_priorities', {})
                for sno_str, priority in temp_priorities.items():
                    todo = Todo.query.filter_by(sno=int(sno_str)).first()
                    if todo:
                        todo.priority = priority
            
            db.session.commit()
            # Clear the session
            session.pop('temp_priorities', None)
            return redirect("/")
        
        elif action == 'cancel':
            # Discard all temporary changes
            session.pop('temp_priorities', None)
            return redirect("/")
        
        sno = int(request.form.get('sno'))
        
        if action == 'up':
            # Move up - decrease priority (only in session)
            temp_priorities = session.get('temp_priorities', {})
            current_priority = temp_priorities.get(str(sno))
            
            if current_priority is not None:
                # Find the todo with the next lower priority
                todos_list = [(k, v) for k, v in temp_priorities.items()]
                todos_sorted = sorted(todos_list, key=lambda x: x[1])
                
                current_index = next(i for i, (k, v) in enumerate(todos_sorted) if k == str(sno))
                if current_index > 0:
                    # Swap with the previous todo
                    prev_sno = todos_sorted[current_index - 1][0]
                    temp_priorities[str(sno)], temp_priorities[prev_sno] = temp_priorities[prev_sno], temp_priorities[str(sno)]
                    session['temp_priorities'] = temp_priorities
        
        elif action == 'down':
            # Move down - increase priority (only in session)
            temp_priorities = session.get('temp_priorities', {})
            current_priority = temp_priorities.get(str(sno))
            
            if current_priority is not None:
                # Find the todo with the next higher priority
                todos_list = [(k, v) for k, v in temp_priorities.items()]
                todos_sorted = sorted(todos_list, key=lambda x: x[1])
                
                current_index = next(i for i, (k, v) in enumerate(todos_sorted) if k == str(sno))
                if current_index < len(todos_sorted) - 1:
                    # Swap with the next todo
                    next_sno = todos_sorted[current_index + 1][0]
                    temp_priorities[str(sno)], temp_priorities[next_sno] = temp_priorities[next_sno], temp_priorities[str(sno)]
                    session['temp_priorities'] = temp_priorities
    
    # Get all todos
    all_todos = Todo.query.order_by(Todo.priority).all()
    
    # If session has temporary priorities, use those; otherwise use database priorities
    if 'temp_priorities' in session:
        temp_priorities = session['temp_priorities']
        # Sort todos based on temporary priorities
        all_todos_with_temp = [(todo, temp_priorities.get(str(todo.sno), todo.priority)) for todo in all_todos]
        all_todos_with_temp.sort(key=lambda x: x[1])
        all_todos = [todo for todo, _ in all_todos_with_temp]
        has_unsaved_changes = True
    else:
        has_unsaved_changes = False
    
    return render_template('change_priority.html', allTodo=all_todos, has_unsaved_changes=has_unsaved_changes)

@app.route('/about')
def about():
    return render_template('about.html')

def init_categories():
    """Initialize default categories if they don't exist"""
    default_categories = ['Work', 'Personal']
    for cat_name in default_categories:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))
    db.session.commit()


def setup_database():
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        todo_columns = [col['name'] for col in inspector.get_columns('todo')]
        if 'completed' not in todo_columns:
            db.session.execute(text('ALTER TABLE todo ADD COLUMN completed BOOLEAN DEFAULT 0'))
            db.session.commit()
        init_categories()


setup_database()

if __name__ == '__main__':
    app.run(debug=True)


