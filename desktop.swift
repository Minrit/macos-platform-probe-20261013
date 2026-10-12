import AppKit
import ApplicationServices
import Metal
import Foundation

let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
let apps = NSWorkspace.shared.runningApplications.filter { $0.bundleIdentifier == "dev.horizyn.app" }.map {
    ["name": $0.localizedName ?? "", "bundle": $0.bundleIdentifier ?? "", "pid": Int($0.processIdentifier)] as [String: Any]
}
let devices = MTLCopyAllDevices().map { $0.name }
let result: [String: Any] = [
    "metalDevices": devices,
    "defaultMetalDevice": MTLCreateSystemDefaultDevice()?.name ?? "NONE",
    "accessibilityTrusted": AXIsProcessTrusted(),
    "screenCapturePreflight": CGPreflightScreenCaptureAccess(),
    "displayID": CGMainDisplayID(),
    "windows": windows,
    "horizynApplications": apps,
]
let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)
