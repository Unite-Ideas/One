# Church Space Calculator

This project aims to provide a simple tool that can be embedded in a WordPress
page. The tool will help architects and church planners estimate the square
footage required for various spaces in a church based on attendance numbers.

## Project Goal

The application will collect the number of adults, youth, children, and babies
in the congregation and calculate how much space is needed for each area of the
building. Additional facilities such as bathrooms, offices, or coffee shops can
be toggled on or off. A global **Space** slider will let you increase or
reduce the total square footage to match specific preferences.

Eventually the calculator will also estimate costs by multiplying the square
footage for each area by an adjustable price per square foot. A report
summarizing the results can be downloaded and saved for each client.

## Example Input

```
Adults: 100
Youth: 10
Children: 10
Babies: 10
Additional areas: bathrooms, offices, classrooms
Space slider: 0 (no adjustment)
```

## Example Output

```
Sanctuary space: 2,000 sq ft (100 adults * 20 sq ft)
Youth space: 100 sq ft (10 youth * 10 sq ft)
Children's space: 50 sq ft (10 kids * 5 sq ft)
Nursery space: 10 sq ft (10 babies * 1 sq ft)
Bathrooms, offices, classrooms: calculated per selected options
Total: 2,160 sq ft (plus any adjustments from the Space slider)
```

## How to Use

1. Place the HTML/JavaScript from this repository into a WordPress page or
   template.
2. Open the page in a browser and enter the attendance numbers.
3. Select any additional areas to include (bathrooms, offices, conference rooms,
   coffee shop, merch store, storage, food pantry, classrooms, etc.).
4. Adjust the **Space** slider as needed.
5. View the detailed listing of square footage and costs, then download the
   report.

## Contributing

This project is in its early stages. Contributions are welcome!

1. Fork the repository and create a new branch for your feature or fix.
2. Submit a pull request describing your changes.
3. Include clear instructions and update this README when appropriate.
