// svgo.config.js
module.exports = {
    multipass: true,
    plugins: [
        "cleanupAttrs",
        "removeDoctype",
        "removeComments",
        "removeMetadata",
        "removeTitle",
        "removeDesc",
        "removeUselessDefs",
        "convertStyleToAttrs",
        "removeDimensions",
        "removeXMLNS",
        "removeXMLProcInst",

        // Preserve group structure
        {
            name: "collapseGroups",
            active: false
        },
        {
            name: "mergePaths",
            active: false
        }
    ]
};
