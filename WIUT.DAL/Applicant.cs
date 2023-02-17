using System;

namespace WIUT.DAL
{
    public class Applicant
    {
        private string name;
        private string surname;
        private string address;
        private DateTime dob;
        private string passportNo;

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

        public string Surname
        {
            get => surname;
            set
            {
                if (string.IsNullOrEmpty(value))
                    throw new Exception("Surname cannot be empty");
                surname = value;
            }
        }

        public string Address
        {
            get => address;
            set
            {
                if (string.IsNullOrEmpty(value))
                    throw new Exception("Address cannot be empty");
                address = value;
            }
        }

        public DateTime DoB
        {
            get => dob;
            set
            {
                if (value.AddYears(18) > DateTime.Now) //not yet 18
                    throw new Exception("Applicant should be at least 18 years old");
                dob = value;
            }
        }

        public bool IsMarried { get; set; }

        public string PassportNo
        {
            get => passportNo;
            set
            {
                if (string.IsNullOrEmpty(value))
                    throw new Exception("Passport No cannot be empty");
                passportNo = value;
            }
        }

        public Course Course { get; set; }

        public Applicant()
        {
        }

        public Applicant(string name, string surname, string address, DateTime doB, bool isMarried, string passportNo, Course course)
        {
            Name = name;
            Surname = surname;
            Address = address;
            DoB = doB;
            IsMarried = isMarried;
            PassportNo = passportNo;
            Course = course;
        }
    }
}