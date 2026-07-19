## 1. Enforce Price-Alert Administration

- [x] 1.1 Update `CurrencyAlertService.create_alert` to validate the current invoker as an administrator of the target chat after existing guards and before exchange-rate fetching or persistence.
- [x] 1.2 Update `CurrencyAlertService.delete_alert` to validate the current invoker as an administrator of the target chat before repository deletion.
- [x] 1.3 Preserve member listing and background alert evaluation paths without adding administrator checks.

## 2. Verify Authorization Behavior

- [x] 2.1 Extend the existing currency-alert service tests to verify administrators can create, reconfigure, and remove alerts through the shared service authorization boundary.
- [x] 2.2 Add service tests proving non-administrators cannot create or reconfigure alerts and that denial occurs before exchange-rate fetching or persistence.
- [x] 2.3 Add a service test proving non-administrators cannot remove alerts and that denial occurs before repository deletion.
- [x] 2.4 Verify private-chat owner authorization delegates to the existing chat-admin validator, while listing and scheduled alert evaluation remain unaffected.

## 3. Quality Checks

- [x] 3.1 Run Ruff and the spacing checker on the changed Python files.
- [x] 3.2 Run the focused currency-alert service tests offline.
- [x] 3.3 Validate the OpenSpec change with `openspec validate restrict-price-alert-management-to-chat-admins --strict`.
