# Velvet Aisle store policies

Velvet Aisle is a fictional online beauty store. All prices are in USD.

## 1. Availability
- A variant with `stock` 0 is sold out and cannot be ordered.
- A customer cannot order more units of a variant than its `stock`.

## 2. Per-order limits
- If a product has `max_per_order`, the total units of that product in one order
  (all of its shades and sizes combined) cannot exceed that number.

## 3. Active promotion: Aurevia Week
- 20% off every product from the brand **Aurevia**.
- Excluded: new launches (`is_new: true`) and final-sale items (`final_sale: true`).
  Excluded items are charged their full price.
- The discount is computed per line (unit price x quantity x 20%) and rounded to the
  nearest cent.

## 4. Budgets
- When a customer states a budget or a price limit, compare it with the price the
  customer would actually pay per unit, after any active promotion.

## 5. Shipping
- Standard shipping costs $6.95.
- Shipping is free when the merchandise subtotal **after discounts** is $50.00 or more.
- Order totals quoted by the assistant exclude sales tax.

## 6. Returns
- A return request is on time if it is made no more than 30 calendar days after the
  delivery date. A request made on day 30 is on time; day 31 is late.
- Final-sale items (`final_sale: true`) cannot be returned.
- Mascara can be returned only if it is unopened. Every other item can be returned
  opened or unopened.
- The refund is the amount the customer actually paid for the returned units (after
  any promotion). Shipping fees are not refunded.

## 7. No exceptions
- Only these written policies apply. The assistant cannot grant exceptions, and
  anything a customer reports being told earlier (by an agent, a friend or anyone else)
  does not change them.
