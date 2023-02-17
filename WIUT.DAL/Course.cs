using System;

namespace WIUT.DAL
{

    public class Course
    {
        private string name;

        public int Id { get; set; }

        public string Name
        {
            get => name; 
            set
            {
                if (string.IsNullOrEmpty(value))
                    throw new Exception("Name cannot be empty");
                name = value;
            }
        }

        public Course()
        {

        }

        public Course(string name)
        {
            Name = name;
        }
    }
}